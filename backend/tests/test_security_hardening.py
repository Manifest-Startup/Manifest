"""Smoke tests for the Task #11 security-hardening modules.

These tests intentionally avoid hitting Postgres so they run on every CI
agent without the migration applied. DB-backed assertions are covered
by integration tests run separately.
"""
from __future__ import annotations


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
            "sessions.manage",           # ditto
        ]
    )
    # API keys must never carry impersonation or session-management
    # scopes — that's a clean separation of duties.
    assert "admin.users.impersonate" not in cleaned
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
