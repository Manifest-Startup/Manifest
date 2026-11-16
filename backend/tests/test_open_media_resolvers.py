"""GraphQL resolvers backed by Open Media: auth gates and response shapes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.graphql.schema import schema
from app.services.integrations.open_media import identity, messaging
from app.services.integrations.open_media.client import OpenMediaNotLinked, OpenMediaUnavailable
from app.services.social import founder_contact


def run(query, *, user="viewer", db=None):
    context = {"db": db or MagicMock(), "request": MagicMock()}
    loop = asyncio.new_event_loop()
    try:
        with (
            patch("app.graphql.schema.get_current_user_id", return_value=user),
            patch("app.graphql.schema.resolve_principal", return_value=SimpleNamespace(has=lambda _: True)),
            patch("app.services.identity.guest_workspace.fetch_user_is_guest", return_value=False),
        ):
            return loop.run_until_complete(schema.execute(query, context_value=context))
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("OPEN_MEDIA_ENABLED", "true")


@pytest.mark.parametrize(
    "operation",
    [
        "query { openMediaLink { linked } }",
        "query { openMediaRealtimeToken { accessToken } }",
        "query { myConversations { conversationId } }",
        "query { unreadMessageCount { count } }",
        'mutation { sendMessage(conversationId: "c", content: "hi") { messageId } }',
        "mutation { disconnectOpenMedia { linked } }",
        'mutation { togglePitchReelLike(reelId: "r", liked: true) { liked } }',
        'mutation { resharePitchReel(reelId: "r", reshared: true) { reshared } }',
    ],
)
def test_open_media_fields_require_a_signed_in_user(operation):
    result = run(operation, user=None)
    assert result.errors and "Authentication required" in result.errors[0].message


def test_open_media_link_reports_status_without_tokens(monkeypatch):
    monkeypatch.setattr(
        identity,
        "link_status",
        lambda uid: {"enabled": True, "linked": True, "handle": "ada", "needs_reconnect": False},
    )
    result = run("query { openMediaLink { enabled linked handle needsReconnect connectUrl } }")
    assert not result.errors
    assert result.data["openMediaLink"] == {
        "enabled": True,
        "linked": True,
        "handle": "ada",
        "needsReconnect": False,
        "connectUrl": "/api/integrations/open-media/connect",
    }


def test_my_conversations_maps_open_media_shape(monkeypatch):
    calls = {}

    def fake_list(uid, app_only=True):
        calls["args"] = (uid, app_only)
        return [
            {
                "id": "c1",
                "other": {"id": "om-ada", "handle": "ada", "display_name": "Ada", "avatar_url": None},
                "context": {"app": "manifest", "idea_id": "i1", "title": "Tidy"},
                "last_message": {"body": "hello", "created_at": "2026-11-01T00:00:00+00:00"},
                "unread_count": 2,
            }
        ]

    monkeypatch.setattr(messaging, "list_conversations", fake_list)
    result = run(
        "query { myConversations { conversationId otherUserId otherUserName otherUserHandle ideaId ideaTitle lastMessagePreview unreadCount } }"
    )
    assert not result.errors
    assert calls["args"] == ("viewer", True)
    assert result.data["myConversations"] == [
        {
            "conversationId": "c1",
            "otherUserId": "om-ada",
            "otherUserName": "Ada",
            "otherUserHandle": "ada",
            "ideaId": "i1",
            "ideaTitle": "Tidy",
            "lastMessagePreview": "hello",
            "unreadCount": 2,
        }
    ]


def test_unlinked_user_sees_the_connect_message(monkeypatch):
    def not_linked(uid, app_only=True):
        raise OpenMediaNotLinked()

    monkeypatch.setattr(messaging, "list_conversations", not_linked)
    result = run("query { myConversations { conversationId } }")
    assert "Connect your Open Media account" in result.errors[0].message


def test_unread_count_never_breaks_the_nav(monkeypatch):
    def down(uid):
        raise OpenMediaUnavailable("down", status=503)

    monkeypatch.setattr(messaging, "unread_count", down)
    assert run("query { unreadMessageCount { count } }").data == {"unreadMessageCount": {"count": 0}}
    monkeypatch.setenv("OPEN_MEDIA_ENABLED", "")
    monkeypatch.setattr(messaging, "unread_count", lambda uid: (_ for _ in ()).throw(AssertionError()))
    assert run("query { unreadMessageCount { count } }").data == {"unreadMessageCount": {"count": 0}}


def test_send_message_marks_result_as_mine(monkeypatch):
    sent = {}

    def fake_send(uid, cid, body, client_id=None):
        sent.update(uid=uid, cid=cid, body=body, client_id=client_id)
        return {"id": "m1", "conversation_id": cid, "sender_id": "om-me", "body": body, "created_at": None}

    monkeypatch.setattr(messaging, "send_message", fake_send)
    result = run('mutation { sendMessage(conversationId: "c1", content: "hi", clientId: "k") { messageId content isMine } }')
    assert not result.errors
    assert result.data["sendMessage"] == {"messageId": "m1", "content": "hi", "isMine": True}
    assert sent == {"uid": "viewer", "cid": "c1", "body": "hi", "client_id": "k"}


def _ideas_db(owner="founder", published=True):
    db = MagicMock()
    chain = db.table.return_value
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = MagicMock(
        data={"idea_id": "i1", "user_id": owner, "title": "Tidy", "is_published": published}
    )
    return db


def test_message_founder_uses_the_founders_open_media_handle(monkeypatch):
    monkeypatch.setattr(identity, "handle_for_user", lambda uid: "ada" if uid == "founder" else None)
    started = {}

    def fake_start(uid, handle, context=None):
        started.update(uid=uid, handle=handle, context=context)
        return {"id": "c1", "other": {"id": "om-ada", "handle": "ada", "display_name": "Ada"}, "context": context}

    monkeypatch.setattr(messaging, "start_conversation", fake_start)
    result = run(
        'mutation { startConversation(otherUserId: "founder", ideaId: "i1") { conversationId ideaId ideaTitle otherUserHandle } }',
        db=_ideas_db(),
    )
    assert not result.errors, result.errors
    assert started["handle"] == "ada"
    assert started["context"]["app"] == "manifest" and started["context"]["idea_id"] == "i1"
    assert result.data["startConversation"]["ideaTitle"] == "Tidy"


def test_message_founder_explains_when_the_founder_has_not_linked(monkeypatch):
    monkeypatch.setattr(identity, "handle_for_user", lambda uid: None)
    monkeypatch.setattr(messaging, "start_conversation", MagicMock(side_effect=AssertionError))
    result = run(
        'mutation { startConversation(otherUserId: "founder", ideaId: "i1") { conversationId } }',
        db=_ideas_db(),
    )
    assert founder_contact.FOUNDER_NOT_LINKED_MESSAGE in result.errors[0].message


def test_message_founder_requires_a_published_idea(monkeypatch):
    monkeypatch.setattr(identity, "handle_for_user", lambda uid: "ada")
    result = run(
        'mutation { startConversation(otherUserId: "founder", ideaId: "i1") { conversationId } }',
        db=_ideas_db(published=False),
    )
    assert "published ideas" in result.errors[0].message


def test_idea_owner_reports_handle_and_can_message(monkeypatch):
    monkeypatch.setattr(identity, "handle_for_user", lambda uid: None)
    data = founder_contact.get_idea_owner(_ideas_db(), "i1", "viewer")
    assert data["is_published"] is True
    assert data["open_media_handle"] is None and data["can_message"] is False
    monkeypatch.setattr(identity, "handle_for_user", lambda uid: "ada")
    assert founder_contact.get_idea_owner(_ideas_db(), "i1", "viewer")["can_message"] is True
    assert founder_contact.get_idea_owner(_ideas_db(), "i1", "founder")["can_message"] is False


def test_disconnect_returns_unlinked_status(monkeypatch):
    removed = []
    monkeypatch.setattr(identity, "unlink", lambda uid: removed.append(uid))
    monkeypatch.setattr(identity, "link_status", lambda uid: {"enabled": True, "linked": False})
    result = run("mutation { disconnectOpenMedia { linked } }")
    assert result.data == {"disconnectOpenMedia": {"linked": False}} and removed == ["viewer"]


def test_realtime_token_query(monkeypatch):
    monkeypatch.setattr(
        messaging,
        "realtime_token",
        lambda uid: {"supabase_url": "u", "anon_key": "a", "access_token": "t", "expires_at": 5, "om_user_id": "om"},
    )
    result = run("query { openMediaRealtimeToken { supabaseUrl anonKey accessToken expiresAt omUserId } }")
    assert result.data["openMediaRealtimeToken"] == {
        "supabaseUrl": "u",
        "anonKey": "a",
        "accessToken": "t",
        "expiresAt": "5",
        "omUserId": "om",
    }


def test_guests_cannot_message(monkeypatch):
    monkeypatch.setattr(messaging, "send_message", MagicMock(side_effect=AssertionError))
    context = {"db": MagicMock(), "request": MagicMock()}
    loop = asyncio.new_event_loop()
    try:
        with (
            patch("app.graphql.schema.get_current_user_id", return_value="guest"),
            patch("app.graphql.schema.resolve_principal", return_value=SimpleNamespace(has=lambda _: True)),
            patch("app.services.identity.guest_workspace.fetch_user_is_guest", return_value=True),
        ):
            result = loop.run_until_complete(
                schema.execute(
                    'mutation { sendMessage(conversationId: "c", content: "hi") { messageId } }',
                    context_value=context,
                )
            )
    finally:
        loop.close()
    assert "Create an account" in result.errors[0].message
