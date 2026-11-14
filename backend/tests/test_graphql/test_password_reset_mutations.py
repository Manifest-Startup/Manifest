"""End-to-end tests for the password reset GraphQL mutations.

These tests instantiate the resolver directly and stub out the
psycopg2 ``get_db_connection`` context manager and the outbound
email send so the flow can be exercised without a live database.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import patch, MagicMock

import jwt
import pytest

from app.auth.replit_auth import SESSION_SECRET, create_session_token
from app.graphql.schema import Mutation
from app.services import password_reset_service as prs
from app.utils import auth_utils
from app.utils.reset_token_utils import generate_reset_token, hash_token


def _run(coro):
    # pytest-asyncio may close the policy loop between sync tests. Each
    # resolver invocation owns its loop and does not need shared loop state.
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_state():
    prs._reset_buckets_for_test()
    yield
    prs._reset_buckets_for_test()


def _make_info(ip: str = "10.1.2.3"):
    request = MagicMock()
    request.client = MagicMock(host=ip)
    request.url = MagicMock(scheme="https", netloc="manifest.test")
    response = MagicMock()
    info = MagicMock()
    info.context = {"request": request, "response": response}
    return info, response


class _FakeCursor:
    """Minimal stand-in for a psycopg2 RealDict cursor."""

    def __init__(self, rows_by_query: List[Dict[str, Any] | None]):
        self._rows = list(rows_by_query)
        self.executed: List[str] = []

    def execute(self, sql, params=None):  # noqa: D401
        self.executed.append(" ".join(sql.split()))
        self._last_sql = sql

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@contextmanager
def _patched_connection(rows: List[Dict[str, Any] | None]):
    cur = _FakeCursor(rows)
    conn = _FakeConn(cur)

    @contextmanager
    def fake_get_db_connection():
        yield conn

    with patch(
        "app.services.password_reset_service.get_db_connection",
        fake_get_db_connection,
    ):
        yield cur


# ---------------------------------------------------------------------------
# request_password_reset
# ---------------------------------------------------------------------------


def test_request_password_reset_unknown_email_returns_generic():
    """Unknown emails must produce the generic response (no enumeration)."""
    info, _ = _make_info()
    sent: List[str] = []

    async def fake_send(*args, **kwargs):
        sent.append("called")
        return True

    with patch(
        "app.services.password_reset_service.find_resettable_user", return_value=None
    ), patch("app.services.email_service.send_password_reset_email", new=fake_send):
        result = _run(
            Mutation().request_password_reset(info, email="nobody@example.com")
        )

    assert result.success is True
    assert "if an account" in result.message.lower()
    assert sent == [], "no email should be sent for unknown emails"


def test_request_password_reset_oauth_only_returns_generic():
    """Accounts with no password_hash (OAuth-only) get the generic response."""
    info, _ = _make_info()
    sent: List[str] = []

    async def fake_send(*args, **kwargs):
        sent.append("called")
        return True

    # find_resettable_user filters out users without a password_hash by design.
    with patch(
        "app.services.password_reset_service.find_resettable_user", return_value=None
    ), patch("app.services.email_service.send_password_reset_email", new=fake_send):
        result = _run(
            Mutation().request_password_reset(info, email="oauth@example.com")
        )

    assert result.success is True
    assert sent == []


def test_request_password_reset_happy_path_sends_email(monkeypatch):
    info, _ = _make_info()
    monkeypatch.setenv("APP_BASE_URL", "https://manifest.test")
    captured: Dict[str, Any] = {}

    async def fake_send(to_email, reset_url):
        captured["to"] = to_email
        captured["url"] = reset_url
        return True

    user_row = {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "email": "real@example.com",
        "password_hash": "x",
        "is_guest": False,
    }

    with patch(
        "app.services.password_reset_service.find_resettable_user", return_value=user_row
    ), patch(
        "app.services.password_reset_service.create_reset_token_for_user",
        return_value="raw-token-abc",
    ), patch(
        "app.services.email_service.send_password_reset_email", new=fake_send
    ):
        result = _run(Mutation().request_password_reset(info, email="real@example.com"))

    assert result.success is True
    assert captured["to"] == "real@example.com"
    assert captured["url"] == "https://manifest.test/auth/reset-password?token=raw-token-abc"


def test_request_password_reset_rate_limit_returns_generic_no_email():
    info, _ = _make_info(ip="10.9.9.9")
    sent: List[str] = []

    async def fake_send(*args, **kwargs):
        sent.append("called")
        return True

    # Exhaust the per-email bucket.
    for _ in range(5):
        prs.check_request_rate_limit("flood@example.com", "10.9.9.9")

    with patch(
        "app.services.password_reset_service.find_resettable_user"
    ) as lookup, patch(
        "app.services.email_service.send_password_reset_email", new=fake_send
    ):
        result = _run(
            Mutation().request_password_reset(info, email="flood@example.com")
        )

    assert result.success is True
    lookup.assert_not_called()
    assert sent == []


# ---------------------------------------------------------------------------
# reset_password
# ---------------------------------------------------------------------------


def _hash_pw(password: str) -> str:
    """Trivial stand-in so we don't depend on bcrypt timing in tests."""
    return f"hashed::{password}"


def test_reset_password_invalid_token_raises():
    info, _ = _make_info(ip="10.1.1.1")
    with _patched_connection([None]):  # SELECT returns nothing
        with patch(
            "app.utils.password_utils.hash_password", side_effect=_hash_pw
        ):
            with pytest.raises(Exception, match="invalid or has expired"):
                _run(
                    Mutation().reset_password(
                        info, token="does-not-exist", new_password="Abcd1234!"
                    )
                )


def test_reset_password_expired_token_raises():
    info, _ = _make_info(ip="10.1.1.2")
    expired_row = {
        "token_id": 1,
        "user_id": "u-1",
        "expires_at": datetime.now(timezone.utc) - timedelta(minutes=1),
        "used_at": None,
    }
    with _patched_connection([expired_row]):
        with patch("app.utils.password_utils.hash_password", side_effect=_hash_pw):
            with pytest.raises(Exception, match="invalid or has expired"):
                _run(
                    Mutation().reset_password(
                        info, token="raw-expired", new_password="Abcd1234!"
                    )
                )


def test_reset_password_already_used_token_raises():
    info, _ = _make_info(ip="10.1.1.3")
    used_row = {
        "token_id": 1,
        "user_id": "u-1",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        "used_at": datetime.now(timezone.utc) - timedelta(seconds=5),
    }
    with _patched_connection([used_row]):
        with patch("app.utils.password_utils.hash_password", side_effect=_hash_pw):
            with pytest.raises(Exception, match="invalid or has expired"):
                _run(
                    Mutation().reset_password(
                        info, token="raw-used", new_password="Abcd1234!"
                    )
                )


def test_reset_password_weak_password_raises():
    info, _ = _make_info(ip="10.1.1.4")
    with patch("app.utils.password_utils.hash_password", side_effect=_hash_pw):
        with pytest.raises(Exception, match="8 characters"):
            _run(Mutation().reset_password(info, token="anything", new_password="x1"))


def test_reset_password_happy_path_returns_fresh_token():
    info, response = _make_info(ip="10.2.2.2")
    user_uuid = "22222222-2222-2222-2222-222222222222"
    rows = [
        # Token lookup
        {
            "token_id": 7,
            "user_id": user_uuid,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            "used_at": None,
        },
        # User update RETURNING
        {"user_id": user_uuid, "email": "alice@example.com", "pwd_iat": 9999999999},
    ]
    with _patched_connection(rows):
        with patch(
            "app.utils.password_utils.hash_password", side_effect=_hash_pw
        ), patch(
            "app.services.password_reset_service.get_password_changed_at_epoch",
            return_value=9999999999,
        ):
            auth_user = _run(
                Mutation().reset_password(
                    info, token="real-raw-token", new_password="StrongPwd123!"
                )
            )

    assert auth_user.user_id == user_uuid
    assert auth_user.email == "alice@example.com"
    assert auth_user.is_guest is False
    decoded = jwt.decode(auth_user.token, SESSION_SECRET, algorithms=["HS256"])
    assert decoded["sub"] == user_uuid
    assert decoded["pwd_iat"] == 9999999999
    set_cookie_keys = {call.kwargs.get("key") for call in response.set_cookie.call_args_list}
    assert {"session_token", "access_token", "manifest_csrf_token"}.issubset(set_cookie_keys)


def test_reset_password_rate_limited():
    info, _ = _make_info(ip="10.3.3.3")
    for _ in range(20):
        prs.check_reset_attempt_rate_limit("10.3.3.3")

    with pytest.raises(Exception, match="Too many attempts"):
        _run(Mutation().reset_password(info, token="x", new_password="Abcd1234!"))


# ---------------------------------------------------------------------------
# JWT invalidation via pwd_iat
# ---------------------------------------------------------------------------


def test_old_session_token_rejected_after_password_change():
    user_id = "33333333-3333-3333-3333-333333333333"
    # Token issued when pwd_iat was 1000.
    with patch(
        "app.services.password_reset_service.get_password_changed_at_epoch",
        return_value=1000,
    ):
        old_token = create_session_token(user_id, email="bob@example.com")

    request = MagicMock()
    request.cookies = {"access_token": old_token}
    request.headers = {}

    # Now the user's password_changed_at has advanced.
    with patch(
        "app.services.password_reset_service.get_password_changed_at_epoch",
        return_value=2000,
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            auth_utils.get_current_user_id(request)
        assert exc_info.value.status_code == 401


def test_old_session_token_rejected_by_replit_auth_helper():
    """`/auth/me` and `/auth/status` go through `get_current_user_from_session`,
    so it must enforce the same `pwd_iat` invalidation rule.
    """
    from app.auth import replit_auth as ra

    user_id = "55555555-5555-5555-5555-555555555555"
    with patch(
        "app.services.password_reset_service.get_password_changed_at_epoch",
        return_value=1000,
    ):
        old_token = create_session_token(user_id, email="dave@example.com")

    request = MagicMock()
    request.cookies = {"session_token": old_token}
    request.headers = {}

    with patch(
        "app.services.password_reset_service.get_password_changed_at_epoch",
        return_value=2000,
    ):
        assert ra.get_current_user_from_session(request) is None


def test_fresh_session_token_accepted_by_replit_auth_helper():
    from app.auth import replit_auth as ra

    user_id = "66666666-6666-6666-6666-666666666666"
    with patch(
        "app.services.password_reset_service.get_password_changed_at_epoch",
        return_value=2000,
    ):
        token = create_session_token(user_id, email="erin@example.com")

    request = MagicMock()
    request.cookies = {"session_token": token}
    request.headers = {}

    with patch(
        "app.services.password_reset_service.get_password_changed_at_epoch",
        return_value=2000,
    ), patch("app.auth.replit_auth.is_session_active", return_value=True):
        payload = ra.get_current_user_from_session(request)
    assert payload is not None
    assert payload["sub"] == user_id


def test_fresh_session_token_accepted():
    user_id = "44444444-4444-4444-4444-444444444444"
    with patch(
        "app.services.password_reset_service.get_password_changed_at_epoch",
        return_value=2000,
    ), patch("app.auth.replit_auth.create_user_session", return_value=None):
        token = create_session_token(user_id, email="carol@example.com")

    request = MagicMock()
    request.cookies = {"access_token": token}
    request.headers = {}

    with patch(
        "app.services.password_reset_service.get_password_changed_at_epoch",
        return_value=2000,
    ), patch("app.utils.auth_utils.is_session_active", return_value=True):
        result = auth_utils.get_current_user_id(request)
    assert result == user_id


# ---------------------------------------------------------------------------
# Atomicity: bad user reference rolls back token consumption
# ---------------------------------------------------------------------------


def test_consume_token_and_reset_password_rolls_back_on_user_missing():
    """If the UPDATE users RETURNING returns no row, we must raise (not silently
    consume the token), so the surrounding transaction rolls back.
    """
    rows = [
        {
            "token_id": 1,
            "user_id": "ghost-user",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            "used_at": None,
        },
        None,  # UPDATE users ... RETURNING -> no row
    ]
    with _patched_connection(rows):
        with pytest.raises(RuntimeError, match="unknown user_id"):
            prs.consume_token_and_reset_password("raw-tok", "hashed::pwd")
