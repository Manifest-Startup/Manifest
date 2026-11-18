"""The person's whole Open Media inbox (``/v1/connected/me/inbox``, Open Media ADR 0044).

Open Media assembles the inbox with the same code its app uses: chats, bridged
chats and email (one conversation per person or company) in one list,
conversations laid out for reading with email as clean text, and replies routed
to the right place (a chat message, or a threaded email from the mailbox that
received it). Manifest only passes it through; nothing here re-implements it
and nothing is stored.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote

from app.services.integrations.open_media import identity
from app.services.integrations.open_media.client import get_client
from app.services.integrations.open_media.messaging import invalidate_unread

MAX_BODY_CHARS = 50_000


def _path(conversation_id: str, suffix: str = "") -> str:
    return f"/inbox/{quote(str(conversation_id), safe='')}{suffix}"


def list_inbox(user_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    body = get_client().connected(
        user_id, "GET", "/inbox", params={"limit": max(1, min(int(limit), 200))}
    )
    return [c for c in body.get("conversations") or [] if isinstance(c, dict)]


def conversation(user_id: str, conversation_id: str) -> dict[str, Any]:
    return get_client().connected(user_id, "GET", _path(conversation_id))


def reply(
    user_id: str,
    conversation_id: str,
    *,
    body: str,
    reply_to_message_id: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    text = (body or "").strip()
    if not text:
        raise ValueError("Write a message first.")
    if len(text) > MAX_BODY_CHARS:
        raise ValueError(f"Messages can be up to {MAX_BODY_CHARS:,} characters.")
    key = client_id or str(uuid.uuid4())
    payload: dict[str, Any] = {"body": text, "client_id": key}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    return get_client().connected(
        user_id,
        "POST",
        _path(conversation_id, "/messages"),
        json=payload,
        headers={"Idempotency-Key": key},
        idempotent=True,
    )


def mark_read(user_id: str, conversation_id: str) -> bool:
    get_client().connected(user_id, "POST", _path(conversation_id, "/read"), idempotent=True)
    om_user_id = identity.om_user_id_for(user_id)
    if om_user_id:
        invalidate_unread([om_user_id])
    return True
