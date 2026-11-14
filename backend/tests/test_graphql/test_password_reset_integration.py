"""End-to-end integration tests for the password reset GraphQL mutations.

Unlike ``test_password_reset_mutations.py``, these tests run the
``request_password_reset`` and ``reset_password`` resolvers against a
real Postgres database (the one pointed at by ``DATABASE_URL``). They
exercise the actual SQL written by the service layer, so a column
rename or a broken migration would surface here before reaching users.

The tests are skipped unless real database integration tests are explicitly
enabled, so the suite still runs in CI jobs that inject production-like secrets
but do not provide a reachable test database.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from unittest.mock import MagicMock

import jwt
import pytest

from app.auth.replit_auth import SESSION_SECRET, create_session_token
from app.db.database import get_db_connection
from app.graphql.schema import Mutation
from app.services import password_reset_service as prs
from app.utils import auth_utils
from app.utils.password_utils import hash_password, verify_password
from app.utils.reset_token_utils import hash_token


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION_TESTS") != "1" or not os.getenv("DATABASE_URL"),
    reason="set RUN_DB_INTEGRATION_TESTS=1 and DATABASE_URL to run password reset integration tests",
)


TEST_EMAIL_DOMAIN = "pwreset-int-test.invalid"


def _run(coro):
    """Run an async resolver from a sync test."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _make_info(ip: str, response: Optional[MagicMock] = None):
    """Build a minimal Strawberry-style ``info`` mock for resolver calls."""
    request = MagicMock()
    request.client = MagicMock(host=ip)
    request.cookies = {}
    request.headers = {}
    request.url = MagicMock(scheme="https", netloc="manifest.test")
    response = response or MagicMock()
    info = MagicMock()
    info.context = {"request": request, "response": response}
    return info, response


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:10]}@{TEST_EMAIL_DOMAIN}"


def _unique_ip() -> str:
    # 198.51.100.0/24 is reserved for documentation/test use (RFC 5737).
    return f"198.51.100.{uuid.uuid4().int % 250 + 1}"


def _create_user(
    email: str,
    *,
    password: Optional[str] = "OldPassword123!",
    is_guest: bool = False,
) -> str:
    """Insert a user row directly. Returns the new user_id (UUID string)."""
    user_id = str(uuid.uuid4())
    pwd_hash = hash_password(password) if password else None
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (user_id, email, password_hash, is_guest, auth_provider)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, email, pwd_hash, is_guest, "manifest"),
            )
        conn.commit()
    return user_id


def _delete_user(user_id: str) -> None:
    """Delete a test user. CASCADE removes its sessions and reset tokens."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM security_audit_events WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        conn.commit()


def _purge_test_rate_limits(ips: List[str], emails: List[str]) -> None:
    """Best-effort wipe of rate-limit rows for the buckets we touched.

    Mirrors the bucket-key scheme used by ``password_reset_service``:
    rows live in ``password_reset_rate_limit_events`` keyed by the raw
    ``bucket_key`` string (not a hash).
    """
    bucket_keys = (
        [f"pwreset:ip:{ip}" for ip in ips]
        + [f"pwreset:attempt:ip:{ip}" for ip in ips]
        + [f"pwreset:email:{email.lower()}" for email in emails]
    )
    if not bucket_keys:
        return
    placeholders = ",".join(["%s"] * len(bucket_keys))
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM password_reset_rate_limit_events "
                    f"WHERE bucket_key IN ({placeholders})",
                    bucket_keys,
                )
            conn.commit()
    except Exception:
        pass


def _count_tokens_for_user(user_id: str) -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS c FROM password_reset_tokens WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone() or {}
    return int(row.get("c") or 0)


def _fetch_token_row(user_id: str) -> Optional[Dict[str, object]]:
    """Return the most recent password_reset_token row for a user."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT token_id, token_hash, expires_at, used_at, request_ip
                FROM password_reset_tokens
                WHERE user_id = %s
                ORDER BY token_id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            return cur.fetchone()


def _fetch_user(user_id: str) -> Dict[str, object]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, email, password_hash, password_changed_at FROM users WHERE user_id = %s",
                (user_id,),
            )
            return cur.fetchone() or {}


def _insert_token(
    user_id: str,
    raw_token: str,
    *,
    expires_at: datetime,
    used_at: Optional[datetime] = None,
) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO password_reset_tokens
                    (user_id, token_hash, expires_at, used_at, request_ip)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, hash_token(raw_token), expires_at, used_at, "127.0.0.1"),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cleanup_users():
    """Track inserted user_ids so we can wipe them (and their cascaded
    rows) after each test, even on failure."""
    created: List[str] = []
    ips: List[str] = []
    emails: List[str] = []

    def _track(user_id: str, *, ip: Optional[str] = None, email: Optional[str] = None):
        created.append(user_id)
        if ip:
            ips.append(ip)
        if email:
            emails.append(email)
        return user_id

    yield _track

    for uid in created:
        try:
            _delete_user(uid)
        except Exception:
            pass
    _purge_test_rate_limits(ips, emails)


@pytest.fixture
def patch_email(monkeypatch):
    """Capture outbound password-reset emails instead of really sending."""
    sent: List[Dict[str, str]] = []

    async def fake_send(to_email: str, reset_url: str) -> bool:
        sent.append({"to": to_email, "url": reset_url})
        return True

    # Patch in BOTH locations: the canonical module and any importer that
    # may have already bound the symbol. The resolver imports lazily inside
    # the function body so patching the canonical module is enough, but
    # patch wider to be safe.
    monkeypatch.setattr(
        "app.services.email_service.send_password_reset_email", fake_send
    )
    return sent


@pytest.fixture
def capture_token(monkeypatch):
    """Wrap ``generate_reset_token`` so the test can read the raw token
    that the resolver hands to the email layer."""
    captured: Dict[str, str] = {}
    from app.utils import reset_token_utils

    real = reset_token_utils.generate_reset_token

    def spy():
        raw, digest = real()
        captured["raw"] = raw
        captured["digest"] = digest
        return raw, digest

    # The service does ``from ... import generate_reset_token`` at module
    # load, so patch the binding inside the service module.
    monkeypatch.setattr(prs, "generate_reset_token", spy)
    return captured


# ---------------------------------------------------------------------------
# request_password_reset
# ---------------------------------------------------------------------------


def test_request_password_reset_unknown_email_returns_generic_no_token(
    cleanup_users, patch_email
):
    ip = _unique_ip()
    email = _unique_email("missing")
    cleanup_users("00000000-0000-0000-0000-000000000000", ip=ip, email=email)
    info, _ = _make_info(ip)

    result = _run(Mutation().request_password_reset(info, email=email))

    assert result.success is True
    assert "if an account" in result.message.lower()
    assert patch_email == []  # no email send for unknown account


def test_request_password_reset_oauth_only_account_returns_generic(
    cleanup_users, patch_email
):
    ip = _unique_ip()
    email = _unique_email("oauth")
    user_id = _create_user(email, password=None)  # OAuth-only: no password_hash
    cleanup_users(user_id, ip=ip, email=email)

    info, _ = _make_info(ip)
    result = _run(Mutation().request_password_reset(info, email=email))

    assert result.success is True
    assert _count_tokens_for_user(user_id) == 0
    assert patch_email == []


def test_request_password_reset_guest_account_returns_generic(
    cleanup_users, patch_email
):
    ip = _unique_ip()
    email = _unique_email("guest")
    user_id = _create_user(email, password="DoesNotMatter1!", is_guest=True)
    cleanup_users(user_id, ip=ip, email=email)

    info, _ = _make_info(ip)
    result = _run(Mutation().request_password_reset(info, email=email))

    assert result.success is True
    assert _count_tokens_for_user(user_id) == 0
    assert patch_email == []


def test_request_password_reset_happy_path_creates_token_and_sends_email(
    monkeypatch, cleanup_users, patch_email, capture_token
):
    monkeypatch.setenv("APP_BASE_URL", "https://manifest.test")
    ip = _unique_ip()
    email = _unique_email("happy")
    user_id = _create_user(email, password="OldPassword123!")
    cleanup_users(user_id, ip=ip, email=email)

    info, _ = _make_info(ip)
    result = _run(Mutation().request_password_reset(info, email=email))

    assert result.success is True
    # A row landed in the DB with the hashed (not raw) token.
    assert _count_tokens_for_user(user_id) == 1
    raw_token = capture_token["raw"]
    token_row = _fetch_token_row(user_id)
    assert token_row is not None
    assert token_row["token_hash"] == hash_token(raw_token)
    assert token_row["used_at"] is None
    assert token_row["expires_at"] > datetime.now(timezone.utc)
    # Email send was attempted with the URL derived from APP_BASE_URL.
    assert len(patch_email) == 1
    assert patch_email[0]["to"] == email
    assert patch_email[0]["url"].startswith(
        "https://manifest.test/auth/reset-password?token="
    )
    assert raw_token in patch_email[0]["url"]


# ---------------------------------------------------------------------------
# reset_password
# ---------------------------------------------------------------------------


def test_reset_password_full_flow_updates_password_and_returns_fresh_jwt(
    monkeypatch, cleanup_users, patch_email, capture_token
):
    """Run the full request -> reset cycle and assert every observable
    side effect: token consumed, password changed, fresh JWT issued, and
    JWTs predating the reset are rejected."""

    monkeypatch.setenv("APP_BASE_URL", "https://manifest.test")
    ip = _unique_ip()
    email = _unique_email("flow")
    user_id = _create_user(email, password="OldPassword123!")
    cleanup_users(user_id, ip=ip, email=email)

    # 1. Mint an "old" JWT before the reset. Backdate ``iat``/``pwd_iat``
    #    to a value clearly older than NOW() so the post-reset comparison
    #    is unambiguous.
    old_iat = int(datetime.now(timezone.utc).timestamp()) - 3600
    old_token = jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "iat": old_iat,
            "pwd_iat": old_iat,
            "exp": datetime.utcnow() + timedelta(days=7),
        },
        SESSION_SECRET,
        algorithm="HS256",
    )

    # 2. Request the reset (uses real DB writes).
    info, _ = _make_info(ip)
    request_result = _run(Mutation().request_password_reset(info, email=email))
    assert request_result.success is True
    raw_token = capture_token["raw"]
    assert raw_token, "Resolver should have generated a token"

    # 3. Consume the token via reset_password.
    info2, response2 = _make_info(ip)
    auth_user = _run(
        Mutation().reset_password(info2, token=raw_token, new_password="BrandNewPwd!9")
    )

    assert auth_user.user_id == user_id
    assert auth_user.email == email
    assert auth_user.is_guest is False
    assert auth_user.token, "Should have minted a fresh session token"
    response2.set_cookie.assert_called()

    # 4. Database side effects: password updated, token marked used,
    #    password_changed_at advanced.
    user_row = _fetch_user(user_id)
    assert user_row.get("password_hash"), "password_hash must be set after reset"
    assert verify_password("BrandNewPwd!9", str(user_row["password_hash"])) is True
    assert verify_password("OldPassword123!", str(user_row["password_hash"])) is False
    pwd_changed_at = user_row.get("password_changed_at")
    assert pwd_changed_at is not None
    token_row = _fetch_token_row(user_id)
    assert token_row is not None
    assert token_row["used_at"] is not None

    # 5. The fresh JWT must carry a ``pwd_iat`` that matches the new
    #    password_changed_at second.
    decoded = jwt.decode(auth_user.token, SESSION_SECRET, algorithms=["HS256"])
    assert decoded["sub"] == user_id
    assert "pwd_iat" in decoded
    assert int(decoded["pwd_iat"]) == int(pwd_changed_at.timestamp())

    # 6. The pre-reset JWT must now be rejected.
    rejected_request = MagicMock()
    rejected_request.cookies = {"access_token": old_token}
    rejected_request.headers = {}
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        auth_utils.get_current_user_id(rejected_request)
    assert exc_info.value.status_code == 401

    # 7. The new JWT is accepted.
    accepted_request = MagicMock()
    accepted_request.cookies = {"access_token": auth_user.token}
    accepted_request.headers = {}
    assert auth_utils.get_current_user_id(accepted_request) == user_id


def test_reset_password_expired_token_is_rejected_and_password_unchanged(
    cleanup_users, patch_email
):
    ip = _unique_ip()
    email = _unique_email("expired")
    user_id = _create_user(email, password="OldPassword123!")
    cleanup_users(user_id, ip=ip, email=email)

    raw = "expired-raw-token-" + uuid.uuid4().hex
    _insert_token(
        user_id,
        raw,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    info, _ = _make_info(ip)
    with pytest.raises(Exception, match="invalid or has expired"):
        _run(Mutation().reset_password(info, token=raw, new_password="BrandNewPwd!9"))

    # Password must still be the original one.
    user_row = _fetch_user(user_id)
    assert verify_password("OldPassword123!", str(user_row["password_hash"])) is True
    # Token row should remain unused (we never consumed it).
    token_row = _fetch_token_row(user_id)
    assert token_row is not None
    assert token_row["used_at"] is None


def test_reset_password_already_used_token_is_rejected(cleanup_users, patch_email):
    ip = _unique_ip()
    email = _unique_email("used")
    user_id = _create_user(email, password="OldPassword123!")
    cleanup_users(user_id, ip=ip, email=email)

    raw = "used-raw-token-" + uuid.uuid4().hex
    used_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    _insert_token(
        user_id,
        raw,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        used_at=used_at,
    )

    info, _ = _make_info(ip)
    with pytest.raises(Exception, match="invalid or has expired"):
        _run(Mutation().reset_password(info, token=raw, new_password="BrandNewPwd!9"))

    # Password unchanged.
    user_row = _fetch_user(user_id)
    assert verify_password("OldPassword123!", str(user_row["password_hash"])) is True
