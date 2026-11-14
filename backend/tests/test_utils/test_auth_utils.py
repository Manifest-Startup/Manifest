import importlib
import time
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
import jwt

from app.auth.current_user import (
    SUPABASE_JWT_SECRET,
    get_current_user_id,
)


def _make_request(cookie_token=None, header_token=None):
    request = Mock()
    cookies = {}
    if cookie_token is not None:
        cookies["session_token"] = cookie_token

    request.cookies.get.side_effect = lambda key: cookies.get(key)
    headers = {}
    if header_token:
        headers["Authorization"] = f"Bearer {header_token}"
    request.headers.get.side_effect = lambda key: headers.get(key)
    return request


def test_get_current_user_id_success_cookie():
    token = jwt.encode({"sub": "test_user_id"}, SUPABASE_JWT_SECRET, algorithm="HS256")
    request = _make_request(cookie_token=token)

    assert get_current_user_id(request) == "test_user_id"


def test_get_current_user_id_success_bearer_header():
    token = jwt.encode({"sub": "header_user"}, SUPABASE_JWT_SECRET, algorithm="HS256")
    request = _make_request(header_token=token)

    assert get_current_user_id(request) == "header_user"


def test_get_current_user_id_no_token():
    request = _make_request()
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing token"


def test_get_current_user_id_invalid_token():
    request = _make_request(cookie_token="invalid-token")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or expired token"


def test_get_current_user_id_expired_token():
    expired = jwt.encode(
        {"sub": "test_user_id", "exp": int(time.time()) - 3600},
        SUPABASE_JWT_SECRET,
        algorithm="HS256",
    )
    request = _make_request(cookie_token=expired)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token has expired"


def test_get_current_user_id_demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    from app.auth import current_user as auth_utils

    auth_utils = importlib.reload(auth_utils)
    token = auth_utils.generate_demo_token("demo-user", "demo@example.com")
    request = _make_request(header_token=token)

    assert auth_utils.get_current_user_id(request) == "demo-user"

    monkeypatch.delenv("DEMO_MODE", raising=False)
    importlib.reload(auth_utils)


def test_demo_user_credentials_fall_back_when_env_keys_are_empty_strings(monkeypatch):
    """`.env` may contain `DEMO_USER_EMAIL=`; getenv must not return '' instead of the default."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USER_ID", "")
    monkeypatch.setenv("DEMO_USER_EMAIL", "")
    monkeypatch.setenv("DEMO_USER_PASSWORD", "")

    import app.auth.current_user as au

    reloaded = importlib.reload(au)
    assert reloaded.DEMO_USER_EMAIL == "hello@manifeststartup.com"
    assert reloaded.DEMO_USER_PASSWORD == "manifest"
    assert reloaded.DEMO_USER_ID == "demo-user-123"
