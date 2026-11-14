"""GraphQL guest account upgrade (email link + password claim)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graphql.schema import Mutation


def _info_authed_guest():
    info = MagicMock()
    info.context = {
        "response": MagicMock(),
        "db": MagicMock(),
        "request": MagicMock(),
    }
    info.context["request"].client = MagicMock()
    info.context["request"].client.host = "127.0.0.1"
    return info


@pytest.mark.asyncio
async def test_request_guest_account_upgrade_email_demo_mode():
    mutation = Mutation()
    info = _info_authed_guest()
    with patch("app.graphql.schema.DEMO_MODE", True), patch("app.graphql.schema.is_test_environment", return_value=False):
        result = await mutation.request_guest_account_upgrade_email(info, "new@example.com")
        assert result.success is True


@pytest.mark.asyncio
async def test_request_guest_account_upgrade_email_creates_token_and_sends():
    mutation = Mutation()
    info = _info_authed_guest()
    with patch("app.graphql.schema.DEMO_MODE", False), patch(
        "app.graphql.schema.is_test_environment", return_value=False
    ), patch("app.graphql.schema.get_current_user_id", return_value="guest-user-id"), patch(
        "app.services.identity.guest_upgrade.create_guest_upgrade_token", return_value="raw-token-xyz"
    ), patch(
        "app.services.identity.guest_upgrade.build_guest_upgrade_url", return_value="https://app.test/auth?t=1"
    ), patch(
        "app.services.integrations.email_sender.send_guest_upgrade_email", new_callable=AsyncMock, return_value=True
    ) as send_mail, patch(
        "app.services.identity.password_reset.check_guest_upgrade_request_rate_limit", return_value=True
    ), patch(
        "app.graphql.schema.record_security_event"
    ):
        result = await mutation.request_guest_account_upgrade_email(info, "founder@example.com")
        assert result.success is True
        send_mail.assert_awaited_once()


@pytest.mark.asyncio
async def test_complete_guest_account_upgrade_sets_session():
    mutation = Mutation()
    info = _info_authed_guest()
    with patch("app.graphql.schema.DEMO_MODE", False), patch(
        "app.graphql.schema.is_test_environment", return_value=False
    ), patch(
        "app.services.identity.guest_upgrade.complete_guest_upgrade",
        return_value=({"user_id": "u1", "email": "e@example.com"}, None),
    ), patch("app.auth.replit_auth.create_session_token", return_value="jwt-token"), patch(
        "app.graphql.schema._set_browser_auth_session"
    ) as set_sess, patch("app.graphql.schema.record_security_event"):
        auth = await mutation.complete_guest_account_upgrade(info, "tok", "Password123!@")
        assert auth.user_id == "u1"
        assert auth.email == "e@example.com"
        assert auth.token == "jwt-token"
        assert auth.is_guest is False
        set_sess.assert_called_once()
