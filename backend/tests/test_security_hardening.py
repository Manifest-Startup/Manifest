"""Smoke tests for the Task #11 security-hardening modules.

These tests intentionally avoid hitting Postgres so they run on every CI
agent without the migration applied. DB-backed assertions are covered
by integration tests run separately.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest


# --- account lockout (logic-only) -----------------------------------------
from app.security import account_lockout as al


def test_backoff_increases_with_attempts():
    a = al._backoff_for(al.EMAIL_MAX_BEFORE_LOCK)
    b = al._backoff_for(al.EMAIL_MAX_BEFORE_LOCK + 5)
    # First lock kicks in at the threshold; subsequent attempts must back off further.
    assert a > 0
    assert b > a


def test_lock_payload_includes_email_and_ip_keys():
    # Just exercise the key normalizer / bucket-name helpers without DB.
    assert al._normalize_email("Foo@Bar.com  ") == "foo@bar.com"
    assert al._normalize_email(None) == "unknown"
    assert al._normalize_ip("203.0.113.5") == "203.0.113.5"
    # IP normalizer collapses missing values to a sentinel so the bucket
    # key is still well-defined when behind a proxy.
    assert al._normalize_ip(None) == "unknown"


# --- breached-passwords (HIBP wrapper, mocked) -----------------------------
from app.security import breached_passwords as bp


class _FakeResp:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class _FakeClient:
    def __init__(self, resp=None, raise_exc: Exception | None = None):
        self._resp = resp
        self._raise = raise_exc

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get(self, *_args, **_kwargs):
        if self._raise:
            raise self._raise
        return self._resp


def test_breached_password_known_breach(monkeypatch):
    """A breached candidate password must trip the HIBP check.

    We mock the network response so the test is hermetic and fast. Force
    the check on (the global suite disables it for hermeticity).
    """
    import hashlib

    monkeypatch.setenv("DISABLE_HIBP_CHECK", "0")
    sha1_full = hashlib.sha1(b"P@ssw0rd").hexdigest().upper()
    suffix = sha1_full[5:]
    fake_body = f"{suffix}:5\nFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF:1\n"
    client = _FakeClient(resp=_FakeResp(200, fake_body))

    with patch("app.security.breached_passwords.httpx.Client", return_value=client):
        assert bp.is_password_breached("P@ssw0rd") is True


def test_breached_password_fail_open_on_network_error(monkeypatch):
    monkeypatch.setenv("DISABLE_HIBP_CHECK", "0")
    client = _FakeClient(raise_exc=RuntimeError("nope"))
    with patch("app.security.breached_passwords.httpx.Client", return_value=client):
        # Fail-open: must NOT block account creation when HIBP is down.
        assert bp.is_password_breached("Sup3r-Str0ng-Pwd!") is False


# --- OIDC verification ----------------------------------------------------
from app.security import oidc_verification as ov


def test_oidc_verify_rejects_garbage_token():
    assert ov.verify_id_token("not.a.jwt", audience="x", issuer="y") is None


def test_oidc_verify_rejects_unsigned_token():
    """Closes SEC-003 — an unsigned (alg=none) token must never be accepted."""
    import jwt

    unsigned = jwt.encode({"sub": "attacker", "aud": "x", "iss": "y"}, "", algorithm="none")
    assert ov.verify_id_token(unsigned, audience="x", issuer="y") is None


# --- API key scope filtering ---------------------------------------------
from app.security.permissions import filter_api_key_scopes


def test_api_key_scopes_strip_forbidden():
    cleaned = filter_api_key_scopes(
        [
            "read",
            "write",
            "admin.users.impersonate",  # explicitly in API_KEY_FORBIDDEN
            "mfa.manage",                # ditto
            "sessions.manage",           # ditto
        ]
    )
    # API keys must never carry impersonation, MFA-management, or
    # session-management scopes — that's a clean separation of duties.
    assert "admin.users.impersonate" not in cleaned
    assert "mfa.manage" not in cleaned
    assert "sessions.manage" not in cleaned
    assert "read" in cleaned and "write" in cleaned


# --- Step-up TTL plumbing -------------------------------------------------
from app.security import step_up


def test_step_up_default_ttl_positive():
    assert step_up.DEFAULT_TTL_SECONDS > 0


# --- API key rotation hash algorithm --------------------------------------
from app.services.identity.api_keys import generate_api_key, _verify_against_stored


def test_api_key_bcrypt_round_trip():
    full, prefix, key_hash, algo = generate_api_key()
    assert full.startswith("manifest_sk_")
    assert len(prefix) == 16
    assert algo in ("bcrypt", "sha256")
    assert _verify_against_stored(full, key_hash, algo) is True
    assert _verify_against_stored(full + "x", key_hash, algo) is False
