"""Direct messages through Open Media (``/v1/connected/me/conversations``).

Manifest lists only conversations tagged ``context.app = "manifest"`` by
default. Unread counts are cached per Open Media user for a few minutes and
dropped by ``message.created`` / ``conversation.read`` webhooks.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote

from app.services.integrations.open_media import identity, settings
from app.services.integrations.open_media.client import get_client, person, pick
from app.services.shared.cache import cache_delete, cache_get, cache_set

UNREAD_TTL_SECONDS = 300
MAX_BODY_CHARS = 4000


def _unread_key(om_user_id: str) -> str:
    return f"open_media:unread:{om_user_id}"


def invalidate_unread(om_user_ids: list[str]) -> None:
    for om_user_id in om_user_ids:
        if om_user_id:
            cache_delete(_unread_key(str(om_user_id)))


def idea_context(idea_id: str, title: str | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {
        "app": settings.APP_TAG,
        "idea_id": str(idea_id),
        "url": f"{settings.app_origin()}/ideas/{idea_id}",
    }
    if title:
        context["title"] = str(title)[:200]
    return context


def _message(raw: dict[str, Any], conversation_id: str = "") -> dict[str, Any]:
    return {
        "id": str(pick(raw, "id", default="")),
        "conversation_id": str(
            pick(raw, "conversation_id", "conversationId", default=conversation_id)
        ),
        "sender_id": str(pick(raw, "sender_id", "senderId", default="")),
        "body": str(pick(raw, "body", "text", default="")),
        "created_at": pick(raw, "created_at", "createdAt"),
        "reply_to_message_id": pick(raw, "reply_to_message_id", "replyToMessageId"),
    }


def _conversation(raw: dict[str, Any], me: str | None) -> dict[str, Any]:
    members = [person(m) for m in (raw.get("members") or [])]
    other = next((m for m in members if m["id"] and m["id"] != me), None)
    other = other or (members[0] if members else person({}))
    last = pick(raw, "last_message", "lastMessage") or {}
    context = raw.get("context") if isinstance(raw.get("context"), dict) else {}
    return {
        "id": str(pick(raw, "id", default="")),
        "kind": pick(raw, "kind"),
        "title": pick(raw, "title"),
        "context": context,
        "other": other,
        "last_message": _message(last) if last else None,
        "unread_count": int(pick(raw, "unread_count", "unreadCount", default=0) or 0),
        "updated_at": pick(raw, "updated_at", "updatedAt"),
    }


def list_conversations(user_id: str, *, app_only: bool = True) -> list[dict[str, Any]]:
    params = {"app": settings.APP_TAG} if app_only else None
    body = get_client().connected(user_id, "GET", "/conversations", params=params)
    me = identity.om_user_id_for(user_id)
    return [_conversation(c, me) for c in body.get("conversations") or [] if isinstance(c, dict)]


def start_conversation(
    user_id: str, *, handle: str, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"handle": handle}
    if context:
        payload["context"] = context
    # Re-uses the existing direct conversation, so a retry cannot create a duplicate.
    body = get_client().connected(user_id, "POST", "/conversations", json=payload, idempotent=True)
    return _conversation(body.get("conversation") or {}, identity.om_user_id_for(user_id))


def list_messages(
    user_id: str, conversation_id: str, *, limit: int = 100, before: str | None = None
) -> list[dict[str, Any]]:
    body = get_client().connected(
        user_id,
        "GET",
        f"/conversations/{quote(conversation_id, safe='')}/messages",
        params={"limit": max(1, min(int(limit), 200)), "before": before},
    )
    return [_message(m, conversation_id) for m in body.get("messages") or [] if isinstance(m, dict)]


def send_message(
    user_id: str, conversation_id: str, *, body: str, client_id: str | None = None
) -> dict[str, Any]:
    text = (body or "").strip()
    if not text:
        raise ValueError("Write a message first.")
    if len(text) > MAX_BODY_CHARS:
        raise ValueError(f"Messages can be up to {MAX_BODY_CHARS:,} characters.")
    key = client_id or str(uuid.uuid4())
    response = get_client().connected(
        user_id,
        "POST",
        f"/conversations/{quote(conversation_id, safe='')}/messages",
        json={"body": text, "client_id": key},
        headers={"Idempotency-Key": key},
        idempotent=True,
    )
    return _message(response.get("message") or {}, conversation_id)


def existing_conversation_with(user_id: str, handle: str) -> str | None:
    """The id of a direct conversation the person already has with ``handle``, or None.
    Never opens one: a new conversation could show up for the other person."""
    wanted = (handle or "").lstrip("@").lower()
    for conversation in list_conversations(user_id, app_only=False):
        other = conversation.get("other") or {}
        if (
            conversation.get("kind") == "direct"
            and str(other.get("handle") or "").lower() == wanted
        ):
            return conversation["id"] or None
    return None


def save_draft(user_id: str, conversation_id: str, *, body: str, ref: str) -> dict[str, Any]:
    """Saves (or updates, by ``ref``) an unsent draft in Open Media (open-media ADR 0045)."""
    response = get_client().connected(
        user_id,
        "POST",
        f"/conversations/{quote(conversation_id, safe='')}/drafts",
        json={"body": body, "app": settings.APP_TAG, "ref": ref},
        idempotent=True,
    )
    return response.get("draft") or {}


def discard_draft(user_id: str, draft_id: str) -> None:
    get_client().connected(user_id, "DELETE", f"/drafts/{quote(draft_id, safe='')}")


def mark_read(user_id: str, conversation_id: str) -> bool:
    get_client().connected(
        user_id, "POST", f"/conversations/{quote(conversation_id, safe='')}/read", idempotent=True
    )
    om_user_id = identity.om_user_id_for(user_id)
    if om_user_id:
        invalidate_unread([om_user_id])
    return True


def unread_count(user_id: str) -> int:
    """Unread messages across the whole inbox: chats and email (cached; webhooks invalidate)."""
    om_user_id = identity.om_user_id_for(user_id)
    if not om_user_id:
        return 0
    cached = cache_get(_unread_key(om_user_id))
    if isinstance(cached, int):
        return cached
    from app.services.integrations.open_media import inbox

    total = sum(int(c.get("unread_count") or 0) for c in inbox.list_inbox(user_id, limit=200))
    cache_set(_unread_key(om_user_id), total, UNREAD_TTL_SECONDS)
    return total


def realtime_token(user_id: str) -> dict[str, Any]:
    """Short-lived Supabase credentials so the browser can subscribe to Realtime."""
    body = get_client().connected(user_id, "POST", "/realtime-token", idempotent=True)
    return {
        "supabase_url": str(pick(body, "supabase_url", "supabaseUrl", default="")),
        "anon_key": str(pick(body, "anon_key", "anonKey", default="")),
        "access_token": str(pick(body, "access_token", "accessToken", default="")),
        "expires_at": pick(body, "expires_at", "expiresAt"),
        "om_user_id": identity.om_user_id_for(user_id),
    }
