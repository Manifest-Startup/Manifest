from unittest.mock import MagicMock

import pytest

from app.graphql.schema import Mutation


def _info_with_response():
    info = MagicMock()
    request = MagicMock()
    request.cookies = {}
    request.headers = {}
    request.client = None
    info.context = {"request": request, "response": MagicMock(), "db": MagicMock()}
    return info


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
