from unittest.mock import MagicMock, patch

import pytest

from app.graphql.schema import Mutation


def _info_with_response():
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
async def test_start_guest_session_disabled_in_demo_mode():
    mutation = Mutation()
    info = _info_with_response()
    with patch("app.graphql.schema.DEMO_MODE", True):
        with pytest.raises(Exception, match="not available in demo mode"):
            await mutation.start_guest_session(info)


@pytest.mark.asyncio
async def test_toggle_publish_rejects_guest_account():
    mutation = Mutation()
    info = MagicMock()
    info.context = {"db": MagicMock(), "request": MagicMock()}
    with patch(
        "app.graphql.schema._require_full_account",
        side_effect=Exception("Create an account to use this feature."),
    ):
        with pytest.raises(Exception, match="Create an account"):
            await mutation.toggle_publish_idea(info, "00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_merge_guest_workspace_propagates_service_errors():
    mutation = Mutation()
    info = MagicMock()
    info.context = {"request": MagicMock(), "db": MagicMock()}
    with patch("app.graphql.schema.get_current_user_id", return_value="target-user"), patch(
        "app.db.database.get_db_connection"
    ) as gdc:
        conn = MagicMock()
        cm = MagicMock()
        cm.__enter__.return_value = conn
        cm.__exit__.return_value = False
        gdc.return_value = cm
        cur = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        conn.cursor.return_value.__exit__.return_value = False
        with patch(
            "app.services.guest_workspace_service.merge_guest_workspace_sql",
            side_effect=Exception("Invalid or expired merge secret"),
        ):
            with pytest.raises(Exception, match="Invalid or expired merge secret"):
                await mutation.merge_guest_workspace(info, "guest-id", "wrong-secret")


def _mock_db_connection_cm(cursor_side_effect=None):
    """Build a get_db_connection() context-manager mock; the cursor's
    execute() optionally raises to simulate a transient DB failure."""
    conn = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = conn
    cm.__exit__.return_value = False
    cur = MagicMock()
    if cursor_side_effect is not None:
        cur.execute.side_effect = cursor_side_effect
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    return cm, cur


@pytest.mark.asyncio
async def test_start_guest_session_retries_transient_insert_failure():
    """The landing CTA must survive one transient DB failure: the resolver
    retries once with a fresh guest identity and still returns a session
    with the 30-day TTL insert."""
    mutation = Mutation()
    info = _info_with_response()

    cm_fail, cur_fail = _mock_db_connection_cm(
        cursor_side_effect=Exception("server closed the connection unexpectedly")
    )
    cm_ok, cur_ok = _mock_db_connection_cm()

    with patch("app.graphql.schema.DEMO_MODE", False), patch(
        "app.db.database.get_db_connection", side_effect=[cm_fail, cm_ok]
    ), patch("app.auth.replit_auth.create_session_token", return_value="jwt-token"), patch(
        "app.graphql.schema._set_browser_auth_session"
    ), patch("app.graphql.schema.record_security_event"):
        result = await mutation.start_guest_session(info)

    assert result.token == "jwt-token"
    assert result.user_id
    assert result.merge_secret
    # The successful attempt ran the guest INSERT with the TTL clause intact.
    sql = cur_ok.execute.call_args[0][0]
    assert "INTERVAL '30 days'" in sql
    assert "is_guest" in sql


@pytest.mark.asyncio
async def test_start_guest_session_fails_after_both_attempts():
    """Two consecutive failures surface the generic error (no partial state)."""
    mutation = Mutation()
    info = _info_with_response()

    cm1, _ = _mock_db_connection_cm(cursor_side_effect=Exception("still down"))
    cm2, _ = _mock_db_connection_cm(cursor_side_effect=Exception("still down"))

    with patch("app.graphql.schema.DEMO_MODE", False), patch(
        "app.db.database.get_db_connection", side_effect=[cm1, cm2]
    ), patch("app.graphql.schema._set_browser_auth_session"), patch(
        "app.graphql.schema.record_security_event"
    ):
        with pytest.raises(Exception, match="Could not start guest session"):
            await mutation.start_guest_session(info)
