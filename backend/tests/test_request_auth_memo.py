"""Auth runs once per request, and session touches are throttled."""

from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth import current_user
from app.services.identity import sessions


def _request(ua: str = "test-agent") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/graphql",
            "headers": [(b"user-agent", ua.encode())],
            "client": ("127.0.0.1", 1234),
        }
    )


def test_user_id_is_resolved_once_per_request(monkeypatch):
    calls = {"n": 0}

    def resolve(_request):
        calls["n"] += 1
        return "user-1"

    monkeypatch.setattr(current_user, "_resolve_current_user_id", resolve)
    request = _request()
    assert current_user.get_current_user_id(request) == "user-1"
    assert current_user.get_current_user_id(request) == "user-1"
    assert current_user.get_current_user_id_optional(request) == "user-1"
    assert calls["n"] == 1
    # A new request validates again.
    assert current_user.get_current_user_id(_request()) == "user-1"
    assert calls["n"] == 2


def test_auth_failure_is_cached_and_reraised(monkeypatch):
    calls = {"n": 0}

    def resolve(_request):
        calls["n"] += 1
        raise HTTPException(status_code=401, detail="Missing token")

    monkeypatch.setattr(current_user, "_resolve_current_user_id", resolve)
    request = _request()
    for _ in range(2):
        with pytest.raises(HTTPException):
            current_user.get_current_user_id(request)
    assert current_user.get_current_user_id_optional(request) is None
    assert calls["n"] == 1


def test_touch_session_is_throttled_unless_client_changes(monkeypatch):
    writes = {"n": 0}

    class _Cursor:
        def execute(self, *_a, **_k):
            writes["n"] += 1

        def fetchone(self):
            return {}

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    class _Conn:
        def cursor(self):
            return _Cursor()

        def commit(self):
            pass

    @contextmanager
    def fake_conn():
        yield _Conn()

    monkeypatch.setattr(sessions, "get_db_connection", fake_conn)
    monkeypatch.setattr(sessions, "_recent_touches", {})

    sessions.touch_session("s1", _request())
    first = writes["n"]
    assert first > 0
    sessions.touch_session("s1", _request())
    assert writes["n"] == first  # within the interval: no write
    sessions.touch_session("s1", _request(ua="other-browser"))
    assert writes["n"] > first  # client changed: written for auditing
