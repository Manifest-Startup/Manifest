"""GraphQL types for features backed by Open Media (messages, account link).

Conversation and message ids, sender ids and ``otherUserId`` are Open Media
ids. Mappers take the normalised dicts from
``app.services.integrations.open_media``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import strawberry
from app.services.integrations.open_media.client import OpenMediaError

CONNECT_PATH = "/api/integrations/open-media/connect"


def _when(value: object | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)


@strawberry.type
class OpenMediaLink:
    enabled: bool
    linked: bool
    needs_reconnect: bool = False
    handle: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    connect_url: str = CONNECT_PATH


@strawberry.type
class OpenMediaRealtimeToken:
    supabase_url: str
    anon_key: str
    access_token: str
    expires_at: str | None = None
    om_user_id: str | None = None


@strawberry.type
class Conversation:
    conversation_id: str
    other_user_id: str
    other_user_name: str
    other_user_handle: str | None = None
    other_user_avatar: str | None = None
    idea_id: str | None = None
    idea_title: str | None = None
    last_message_at: datetime
    last_message_preview: str | None = None
    unread_count: int = 0


@strawberry.type
class Message:
    message_id: str
    conversation_id: str
    sender_id: str
    content: str
    created_at: datetime
    is_mine: bool = False


@strawberry.type
class UnreadCount:
    count: int


def map_link(status: dict[str, Any]) -> OpenMediaLink:
    return OpenMediaLink(
        enabled=bool(status.get("enabled")),
        linked=bool(status.get("linked")),
        needs_reconnect=bool(status.get("needs_reconnect")),
        handle=status.get("handle"),
        display_name=status.get("display_name"),
        avatar_url=status.get("avatar_url"),
    )


def map_conversation(conv: dict[str, Any]) -> Conversation:
    other = conv.get("other") or {}
    context = conv.get("context") or {}
    last = conv.get("last_message") or {}
    preview = str(last.get("body") or "")[:140] or None
    return Conversation(
        conversation_id=str(conv.get("id") or ""),
        other_user_id=str(other.get("id") or ""),
        other_user_name=str(
            other.get("display_name")
            or other.get("handle")
            or conv.get("title")
            or "Open Media user"
        ),
        other_user_handle=other.get("handle") or None,
        other_user_avatar=other.get("avatar_url"),
        idea_id=context.get("idea_id"),
        idea_title=context.get("title"),
        last_message_at=_when(last.get("created_at") or conv.get("updated_at")),
        last_message_preview=preview,
        unread_count=int(conv.get("unread_count") or 0),
    )


def map_message(msg: dict[str, Any], me_om_id: str | None) -> Message:
    sender = str(msg.get("sender_id") or "")
    return Message(
        message_id=str(msg.get("id") or ""),
        conversation_id=str(msg.get("conversation_id") or ""),
        sender_id=sender,
        content=str(msg.get("body") or ""),
        created_at=_when(msg.get("created_at")),
        is_mine=bool(me_om_id and sender == me_om_id),
    )


async def call_open_media(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a blocking adapter call off the event loop; surface its user-safe message."""
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except (OpenMediaError, ValueError) as exc:
        raise Exception(str(exc)) from exc
