"""Replit OIDC ID token signature verification (SEC-003).

The previous implementation called ``jwt.decode(id_token, options={"verify_signature": False})``,
which accepts forged tokens. This module fetches the IdP JWKS, caches it,
verifies signature + audience + issuer + nonce + expiry, and exposes a
single ``verify_id_token()`` entry point.

Cache strategy:
- JWKS is fetched on first use and cached for 1 hour.
- On a `kid` miss the cache is force-refreshed exactly once.

Failure mode: returns ``None`` and logs. Never raises into the auth flow
so a transient JWKS outage degrades to "login fails", not "exception".
"""

from __future__ import annotations

import os
import time
from threading import Lock
from typing import Any

import httpx
import jwt
from app.utils.logger import logger
from jwt import PyJWKClient

_DEFAULT_ISSUER = "https://replit.com/oidc"
_JWKS_TTL_SECONDS = 3600

_jwks_cache: dict[str, dict[str, Any]] = {}
_jwks_lock = Lock()


def _discover_jwks_uri(issuer: str) -> str | None:
    """Fetch /.well-known/openid-configuration to locate jwks_uri.

    Cached implicitly by virtue of being called only on cache rebuild.
    """
    well_known = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(well_known)
            if resp.status_code != 200:
                logger.warning(
                    "[oidc] OIDC discovery failed: %s -> %s", well_known, resp.status_code
                )
                return None
            return resp.json().get("jwks_uri")
    except Exception as exc:
        logger.error("[oidc] OIDC discovery error: %s", exc)
        return None


def _get_jwk_client(issuer: str, *, force_refresh: bool = False) -> PyJWKClient | None:
    now = time.time()
    with _jwks_lock:
        cached = _jwks_cache.get(issuer)
        if cached and not force_refresh and (now - cached["fetched_at"] < _JWKS_TTL_SECONDS):
            return cached["client"]

        jwks_uri = _discover_jwks_uri(issuer)
        if not jwks_uri:
            return None
        try:
            client = PyJWKClient(jwks_uri, cache_keys=True, lifespan=_JWKS_TTL_SECONDS)
            _jwks_cache[issuer] = {"client": client, "fetched_at": now}
            return client
        except Exception as exc:
            logger.error("[oidc] Failed to construct PyJWKClient for %s: %s", jwks_uri, exc)
            return None


def verify_id_token(  # noqa: C901
    id_token: str,
    *,
    audience: str | None = None,
    issuer: str | None = None,
    nonce: str | None = None,
    leeway: int = 30,
) -> dict[str, Any] | None:
    """Verify an OIDC ID token's signature, issuer, audience, expiry, and nonce.

    Returns the validated claims dict, or ``None`` if verification fails.
    """
    if not id_token:
        return None

    issuer = issuer or os.getenv("ISSUER_URL", _DEFAULT_ISSUER)
    audience = audience or os.getenv("REPL_ID")

    if not audience:
        logger.error("[oidc] verify_id_token called without an audience (REPL_ID unset)")
        return None

    client = _get_jwk_client(issuer)
    if client is None:
        return None

    def _attempt(attempt_client: PyJWKClient) -> dict[str, Any] | None:
        try:
            signing_key = attempt_client.get_signing_key_from_jwt(id_token)
        except Exception as exc:
            logger.warning("[oidc] No signing key for kid: %s", exc)
            return None
        try:
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256", "ES256", "RS512", "ES384"],
                audience=audience,
                issuer=issuer,
                leeway=leeway,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
        except jwt.ExpiredSignatureError:
            logger.info("[oidc] ID token expired")
            return None
        except jwt.InvalidAudienceError:
            logger.warning("[oidc] ID token audience mismatch (expected %s)", audience)
            return None
        except jwt.InvalidIssuerError:
            logger.warning("[oidc] ID token issuer mismatch (expected %s)", issuer)
            return None
        except Exception as exc:
            logger.warning("[oidc] ID token verification failed: %s", exc)
            return None

        if nonce is not None:
            token_nonce = claims.get("nonce")
            if not token_nonce or token_nonce != nonce:
                logger.warning("[oidc] ID token nonce mismatch")
                return None
        return claims

    # First try cached JWKS, then refresh once on signing-key miss
    claims = _attempt(client)
    if claims is not None:
        return claims

    refreshed = _get_jwk_client(issuer, force_refresh=True)
    if refreshed is None or refreshed is client:
        return None
    return _attempt(refreshed)


def clear_cache_for_test() -> None:  # pragma: no cover - test helper
    with _jwks_lock:
        _jwks_cache.clear()
