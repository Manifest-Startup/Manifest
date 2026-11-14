"""Tests for tiered rate-limit enforcement (SEC-007)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.security import rate_limit_policies as rlp


class _FakeRateLimit:
    def __init__(self):
        self.calls: list[tuple[str, int, int]] = []
        self._counts: dict[str, int] = {}
        self.limits: dict[str, int] = {}

    def allow(self, bucket_key: str, *, limit: int, window_seconds: int) -> bool:
        self.calls.append((bucket_key, limit, window_seconds))
        self._counts[bucket_key] = self._counts.get(bucket_key, 0) + 1
        self.limits[bucket_key] = limit
        return self._counts[bucket_key] <= limit


@pytest.fixture()
def fake_limiter(monkeypatch):
    fake = _FakeRateLimit()
    monkeypatch.setattr(rlp, "rate_limit_service", fake)
    return fake


def _request_with_ip(ip: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
        "client": (ip, 0),
        "path": "/",
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_enforce_consumes_per_ip_and_per_user_buckets(fake_limiter):
    req = _request_with_ip("8.8.8.8")
    rlp.enforce_rate_limit(req, "login", tier=rlp.TIER_AUTH, user_id="u-1")

    assert len(fake_limiter.calls) == 2
    bucket_prefixes = {key.split(":", 3)[1] for key, _, _ in fake_limiter.calls}
    assert bucket_prefixes == {"auth"}


def test_enforce_raises_429_when_ip_bucket_full(fake_limiter):
    req = _request_with_ip("8.8.8.8")
    tier = rlp.TIER_AUTH
    # Drain the per-IP allowance.
    for _ in range(tier.per_ip_limit):
        rlp.enforce_rate_limit(req, "login", tier=tier)
    with pytest.raises(HTTPException) as excinfo:
        rlp.enforce_rate_limit(req, "login", tier=tier)
    assert excinfo.value.status_code == 429
    assert "Retry-After" in excinfo.value.headers


def _request_with_headers(client_ip: str, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "headers": headers,
        "client": (client_ip, 0),
        "path": "/",
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
    })


def test_x_forwarded_for_ignored_when_peer_not_trusted(fake_limiter, monkeypatch):
    """Without TRUSTED_PROXY_CIDRS, XFF must NOT influence the limiter identity."""
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    # Two requests from the same direct peer but with different spoofed XFF
    # values must hit the SAME bucket (i.e., spoofing fails).
    req_a = _request_with_headers("8.8.8.8", [(b"x-forwarded-for", b"1.1.1.1")])
    req_b = _request_with_headers("8.8.8.8", [(b"x-forwarded-for", b"2.2.2.2")])
    rlp.enforce_rate_limit(req_a, "login", tier=rlp.TIER_AUTH)
    rlp.enforce_rate_limit(req_b, "login", tier=rlp.TIER_AUTH)
    ip_buckets = {k for k, _, _ in fake_limiter.calls if "auth:ip" in k}
    assert len(ip_buckets) == 1, "XFF must be ignored when peer is not a trusted proxy"


def test_x_forwarded_for_honored_when_peer_is_trusted(fake_limiter, monkeypatch):
    """With TRUSTED_PROXY_CIDRS set and peer in range, the right-most XFF wins."""
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    # Right-most entry is the one appended by our trusted proxy (the real client).
    req = _request_with_headers(
        "10.0.0.1",
        [(b"x-forwarded-for", b"66.66.66.66, 203.0.113.5")],
    )
    rlp.enforce_rate_limit(req, "login", tier=rlp.TIER_AUTH)
    # Issue another request with a *different* attacker-prepended value but
    # the same real client; both should land in the same bucket.
    req2 = _request_with_headers(
        "10.0.0.1",
        [(b"x-forwarded-for", b"9.9.9.9, 203.0.113.5")],
    )
    rlp.enforce_rate_limit(req2, "login", tier=rlp.TIER_AUTH)
    ip_buckets = {k for k, _, _ in fake_limiter.calls if "auth:ip" in k}
    assert len(ip_buckets) == 1


def test_attacker_cannot_bypass_per_ip_limit_via_spoofed_xff(fake_limiter, monkeypatch):
    """Untrusted client rotating XFF must still exhaust the same bucket."""
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    tier = rlp.TIER_AUTH
    for i in range(tier.per_ip_limit):
        req = _request_with_headers(
            "8.8.8.8",
            [(b"x-forwarded-for", f"7.7.7.{i}".encode())],
        )
        rlp.enforce_rate_limit(req, "login", tier=tier)
    blocked = _request_with_headers(
        "8.8.8.8",
        [(b"x-forwarded-for", b"7.7.7.250")],
    )
    with pytest.raises(HTTPException) as excinfo:
        rlp.enforce_rate_limit(blocked, "login", tier=tier)
    assert excinfo.value.status_code == 429


def test_weight_consumes_multiple_tokens(fake_limiter):
    req = _request_with_ip("8.8.8.8")
    rlp.enforce_rate_limit(req, "expensive", tier=rlp.TIER_AI, weight=3)
    # weight=3 -> 3 IP allow() calls (no user bucket without user_id).
    assert len(fake_limiter.calls) == 3


def test_get_tier_returns_default_for_unknown_name():
    assert rlp.get_tier("nope") is rlp.TIER_DEFAULT


def test_integration_with_fastapi_dependency(fake_limiter):
    app = FastAPI()

    @app.get("/login")
    def login(request: Request):
        rlp.enforce_rate_limit(request, "login", tier=rlp.TIER_AUTH)
        return {"ok": True}

    client = TestClient(app)
    for _ in range(rlp.TIER_AUTH.per_ip_limit):
        assert client.get("/login").status_code == 200
    blocked = client.get("/login")
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")
