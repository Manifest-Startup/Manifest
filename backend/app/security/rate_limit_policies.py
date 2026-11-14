"""Tiered rate-limit policies (SEC-007).

Provides a single entry point ``enforce_rate_limit(request, scope, tier)``
so that auth, AI, doc-generation, file-upload and "default" routes share
consistent buckets backed by ``rate_limit_service``. The actual limits
come from a small policy table that operations can override via env.

Each tier defines:

- ``per_user_limit`` / ``per_user_window`` — applied when we have a user_id.
- ``per_ip_limit`` / ``per_ip_window``     — always applied as a backstop.
- ``cost_factor``                          — multiplier; an "expensive"
  operation can pass ``weight=N`` so it consumes N tokens per call.

When a bucket is exhausted we raise HTTP 429 with ``Retry-After`` so
clients back off cleanly.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
from dataclasses import dataclass

from app.services.rate_limit_service import rate_limit_service
from fastapi import HTTPException, Request, status

# --- Tier catalog ---------------------------------------------------------


@dataclass(frozen=True)
class _Policy:
    name: str
    per_user_limit: int
    per_user_window: int
    per_ip_limit: int
    per_ip_window: int


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(int(raw), 1)
    except ValueError:
        return default


def _policy(name: str, defaults: tuple[int, int, int, int]) -> _Policy:
    pul, puw, pil, piw = defaults
    return _Policy(
        name=name,
        per_user_limit=_env_int(f"RATE_LIMIT_{name.upper()}_USER_LIMIT", pul),
        per_user_window=_env_int(f"RATE_LIMIT_{name.upper()}_USER_WINDOW", puw),
        per_ip_limit=_env_int(f"RATE_LIMIT_{name.upper()}_IP_LIMIT", pil),
        per_ip_window=_env_int(f"RATE_LIMIT_{name.upper()}_IP_WINDOW", piw),
    )


# Tier defaults: (user_limit, user_window_s, ip_limit, ip_window_s)
TIER_AUTH = _policy("auth", (10, 900, 30, 900))  # login/signup/password
TIER_AI = _policy("ai", (60, 60, 120, 60))  # chat / completion
TIER_DOC_GEN = _policy("doc_gen", (30, 300, 60, 300))  # heavy generators
TIER_UPLOAD = _policy("upload", (40, 60, 80, 60))  # file upload
TIER_VOICE = _policy("voice", (30, 60, 60, 60))  # streaming voice
TIER_DEFAULT = _policy("default", (300, 60, 600, 60))  # everything else


_TIERS_BY_NAME = {
    "auth": TIER_AUTH,
    "ai": TIER_AI,
    "doc_gen": TIER_DOC_GEN,
    "upload": TIER_UPLOAD,
    "voice": TIER_VOICE,
    "default": TIER_DEFAULT,
}


def get_tier(name: str) -> _Policy:
    return _TIERS_BY_NAME.get(name, TIER_DEFAULT)


# --- Enforcement ----------------------------------------------------------


def _parse_trusted_proxies() -> list[ipaddress._BaseNetwork]:
    """Parse ``TRUSTED_PROXY_CIDRS`` (comma-separated CIDRs/IPs) into networks.

    Forwarding headers (``X-Forwarded-For``, ``X-Real-IP``) are honored only
    when the immediate peer is contained in one of these networks. This
    prevents trivial spoofing when the app is reached directly.
    """
    raw = (os.getenv("TRUSTED_PROXY_CIDRS") or "").strip()
    if not raw:
        return []
    nets: list[ipaddress._BaseNetwork] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            nets.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            continue
    return nets


def _is_trusted_peer(peer: str, nets: list[ipaddress._BaseNetwork]) -> bool:
    if not nets or not peer:
        return False
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(addr in net for net in nets)


def _first_valid_ip(value: str) -> str | None:
    """Return the right-most* untrusted candidate from an XFF chain.

    *Right-most* because the right end of XFF is the value appended by our
    own trusted proxy and therefore represents the real client; the left
    end is fully attacker-controlled. We still validate it parses as an IP.
    """
    for candidate in reversed([p.strip() for p in value.split(",") if p.strip()]):
        try:
            ipaddress.ip_address(candidate)
            return candidate
        except ValueError:
            continue
    return None


def _client_ip(request: Request) -> str:
    peer = (request.client.host if request.client else "") or ""
    trusted = _parse_trusted_proxies()

    if _is_trusted_peer(peer, trusted):
        forwarded = request.headers.get("x-forwarded-for") or ""
        if forwarded:
            ip = _first_valid_ip(forwarded)
            if ip:
                return ip
        real = (request.headers.get("x-real-ip") or "").strip()
        if real:
            try:
                ipaddress.ip_address(real)
                return real
            except ValueError:
                pass

    return peer or "unknown"


def _bucket_key(prefix: str, scope: str, identifier: str) -> str:
    digest = hashlib.sha256(f"{scope}:{identifier}".encode()).hexdigest()[:16]
    return f"{prefix}:{scope}:{digest}"


def enforce_rate_limit(
    request: Request,
    scope: str,
    *,
    tier: _Policy = TIER_DEFAULT,
    user_id: str | None = None,
    weight: int = 1,
) -> None:
    """Consume one (or ``weight``) tokens from the per-user and per-IP buckets.

    Raises ``HTTPException(429)`` with a ``Retry-After`` header on exhaustion.
    """
    weight = max(int(weight or 1), 1)

    # Per-IP bucket (always applied).
    ip = _client_ip(request)
    ip_key = _bucket_key(f"rl:{tier.name}:ip", scope, ip)
    for _ in range(weight):
        if not rate_limit_service.allow(
            ip_key,
            limit=tier.per_ip_limit,
            window_seconds=tier.per_ip_window,
        ):
            _raise_429(scope, tier.per_ip_window)

    if user_id:
        user_key = _bucket_key(f"rl:{tier.name}:user", scope, str(user_id))
        for _ in range(weight):
            if not rate_limit_service.allow(
                user_key,
                limit=tier.per_user_limit,
                window_seconds=tier.per_user_window,
            ):
                _raise_429(scope, tier.per_user_window)


def _raise_429(scope: str, retry_after_seconds: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error": "rate_limited",
            "scope": scope,
            "retry_after_seconds": int(retry_after_seconds),
        },
        headers={
            "Retry-After": str(int(retry_after_seconds)),
            "X-RateLimit-Scope": scope,
        },
    )
