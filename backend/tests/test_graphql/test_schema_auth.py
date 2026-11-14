import uuid
from unittest.mock import ANY, MagicMock, patch

import pytest

from app.graphql.schema import Mutation
from app.utils.password_utils import hash_password


def _mock_db_conn_with_cursor(cursor: MagicMock):
    """Build a get_db_connection-compatible context manager mock."""
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False

    cm = MagicMock()
    cm.__enter__.return_value = conn
    cm.__exit__.return_value = False
    return cm, conn


def _info_with_response():
    info = MagicMock()
    request = MagicMock()
    request.cookies = {}
    request.headers = {}
    request.client = None
    info.context = {"request": request, "response": MagicMock(), "db": MagicMock()}
    return info


def _assert_auth_cookies_set(response: MagicMock) -> None:
    response.set_cookie.assert_any_call(
        key="session_token",
        value=ANY,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
        max_age=7 * 24 * 60 * 60,
    )
    response.set_cookie.assert_any_call(
        key="access_token",
        value=ANY,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
        max_age=7 * 24 * 60 * 60,
    )
    assert response.set_cookie.call_count == 3


@pytest.mark.asyncio
async def test_login_demo_mode_success():
    mutation = Mutation()
    info = _info_with_response()

    with patch("app.graphql.schema.DEMO_MODE", True), \
         patch("app.graphql.schema.DEMO_USER_EMAIL", "hello@manifeststartup.com"), \
         patch("app.graphql.schema.DEMO_USER_PASSWORD", "manifest"), \
         patch("app.graphql.schema.generate_demo_token", return_value="demo-token"), \
         patch("app.graphql.schema.ensure_user_record") as ensure_user_record:
        result = await mutation.login_user(info, "hello@manifeststartup.com", "manifest")

    assert result.token == "demo-token"
    assert result.email == "hello@manifeststartup.com"
    ensure_user_record.assert_called_once()
    _assert_auth_cookies_set(info.context["response"])


@pytest.mark.asyncio
async def test_login_demo_mode_invalid_credentials():
    mutation = Mutation()
    info = _info_with_response()

    with patch("app.graphql.schema.DEMO_MODE", True), \
         patch("app.graphql.schema.DEMO_USER_EMAIL", "hello@manifeststartup.com"), \
         patch("app.graphql.schema.DEMO_USER_PASSWORD", "manifest"):
        with pytest.raises(Exception, match="Invalid email or password"):
            await mutation.login_user(info, "wrong@example.com", "wrong-password")


@pytest.mark.asyncio
async def test_login_successful_postgres():
    mutation = Mutation()
    info = _info_with_response()

    password_hash = hash_password("Password123!")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "user_id": "user-123",
        "email": "test@example.com",
        "password_hash": password_hash,
        "is_guest": False,
    }
    conn_cm, _ = _mock_db_conn_with_cursor(cursor)

    with patch("app.graphql.schema.DEMO_MODE", False), \
         patch("app.db.database.get_db_connection", return_value=conn_cm), \
         patch("app.auth.replit_auth.create_session_token", return_value="session-token"):
        result = await mutation.login_user(info, "test@example.com", "Password123!")

    assert result.user_id == "user-123"
    assert result.email == "test@example.com"
    assert result.token == "session-token"
    assert result.is_guest is False
    _assert_auth_cookies_set(info.context["response"])


@pytest.mark.asyncio
async def test_login_invalid_password():
    mutation = Mutation()
    info = _info_with_response()

    password_hash = hash_password("Password123!")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "user_id": "user-123",
        "email": "test@example.com",
        "password_hash": password_hash,
        "is_guest": False,
    }
    conn_cm, _ = _mock_db_conn_with_cursor(cursor)

    with patch("app.graphql.schema.DEMO_MODE", False), \
         patch("app.db.database.get_db_connection", return_value=conn_cm):
        with pytest.raises(Exception, match="Invalid email or password"):
            await mutation.login_user(info, "test@example.com", "bad-password")


@pytest.mark.asyncio
async def test_signup_successful_postgres():
    mutation = Mutation()
    info = _info_with_response()

    cursor = MagicMock()
    cursor.fetchone.return_value = None  # no existing user
    conn_cm, conn = _mock_db_conn_with_cursor(cursor)

    with patch("app.graphql.schema.DEMO_MODE", False), \
         patch("app.db.database.get_db_connection", return_value=conn_cm), \
         patch("app.auth.replit_auth.create_session_token", return_value="signup-token"), \
         patch("uuid.uuid4", return_value=uuid.UUID("11111111-1111-1111-1111-111111111111")):
        result = await mutation.signup_user(info, "new@example.com", "Password123!")

    assert result.user_id == "11111111-1111-1111-1111-111111111111"
    assert result.email == "new@example.com"
    assert result.token == "signup-token"
    assert cursor.execute.call_count >= 2
    conn.commit.assert_called()


@pytest.mark.asyncio
async def test_signup_existing_user_fails():
    mutation = Mutation()
    info = _info_with_response()

    cursor = MagicMock()
    cursor.fetchone.return_value = {"user_id": "existing-user"}
    conn_cm, _ = _mock_db_conn_with_cursor(cursor)

    with patch("app.graphql.schema.DEMO_MODE", False), \
         patch("app.db.database.get_db_connection", return_value=conn_cm):
        with pytest.raises(Exception, match="already exists"):
            await mutation.signup_user(info, "existing@example.com", "Password123!")


@pytest.mark.asyncio
async def test_logout_user_clears_session_and_access_cookies():
    mutation = Mutation()
    info = _info_with_response()

    result = await mutation.logout_user(info)

    assert result is True
    response = info.context["response"]
    response.delete_cookie.assert_any_call(key="session_token", path="/", secure=False, samesite="lax")
    response.delete_cookie.assert_any_call(key="access_token", path="/", secure=False, samesite="lax")
    response.delete_cookie.assert_any_call(key="manifest_csrf_token", path="/", secure=False, samesite="lax")
    assert response.delete_cookie.call_count == 3
