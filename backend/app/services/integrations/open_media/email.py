"""The person's email through Open Media (``GET /v1/connected/me/email``), read-only.

Open Media stores mail from the mailboxes the person connected there. Manifest
reads it live for the Messages page and never stores it: no database rows and
no cache. Replying and marking mail read happen in Open Media, because
``/v1/connected`` exposes only the read route.

Open Media returns a flat list, newest first. Messages are grouped into threads
by ``In-Reply-To`` where the parent is in the list, and otherwise by mailbox plus
the subject with its ``Re:``/``Fwd:`` prefixes removed.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.services.integrations.open_media.client import get_client

MAX_EMAILS = 500
MAX_TEXT_CHARS = 20_000
_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw|sv|antw)\s*(\[\d+\])?\s*:\s*)+", re.IGNORECASE)
_ADDRESS = re.compile(r"^\s*\"?(?P<name>[^\"<]*?)\"?\s*<(?P<email>[^>]+)>\s*$")


def _subject_key(subject: str) -> str:
    return re.sub(r"\s+", " ", _PREFIX.sub("", subject or "")).strip().lower()


def sender_name(sender: str) -> str:
    """``"Ada L" <ada@x.com>`` -> ``Ada L``; a bare address stays as it is."""
    match = _ADDRESS.match(sender or "")
    if match:
        return match.group("name").strip() or match.group("email").strip()
    return (sender or "").strip() or "Unknown sender"


def _email(raw: dict[str, Any]) -> dict[str, Any]:
    to = raw.get("to")
    return {
        "message_id": str(raw.get("messageId") or raw.get("message_id") or ""),
        "in_reply_to": raw.get("inReplyTo") or raw.get("in_reply_to") or None,
        "mailbox_id": str(raw.get("mailboxId") or raw.get("mailbox_id") or ""),
        "account": str(raw.get("account") or ""),
        "folder": str(raw.get("folder") or ""),
        "from": str(raw.get("from") or ""),
        "to": [str(x) for x in to] if isinstance(to, list) else [],
        "subject": str(raw.get("subject") or ""),
        "text": str(raw.get("text") or "")[:MAX_TEXT_CHARS],
        "sent_at": raw.get("sentAt") or raw.get("sent_at"),
        "sender_verified": raw.get("senderVerified") is True,
        "attachments": int(raw.get("attachments") or 0),
    }


def _thread_id(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def list_email(user_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
    """Recent email, newest first, normalised."""
    body = get_client().connected(
        user_id, "GET", "/email", params={"limit": max(1, min(int(limit), MAX_EMAILS))}
    )
    rows = body.get("data") if isinstance(body, dict) else None
    return [_email(row) for row in rows or [] if isinstance(row, dict)]


def group_threads(emails: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group normalised emails into threads, newest thread first, messages oldest first."""
    by_message_id = {e["message_id"]: e for e in emails if e["message_id"]}
    keys: dict[int, str] = {}

    def key_of(email: dict[str, Any], seen: frozenset[str] = frozenset()) -> str:
        cached = keys.get(id(email))
        if cached:
            return cached
        parent = by_message_id.get(email["in_reply_to"] or "")
        if parent is not None and parent is not email and parent["message_id"] not in seen:
            key = key_of(parent, seen | {email["message_id"]})
        else:
            subject = _subject_key(email["subject"])
            key = (
                f"{email['mailbox_id']}|{subject}"
                if subject
                else f"{email['mailbox_id']}|id:{email['message_id'] or id(email)}"
            )
        keys[id(email)] = key
        return key

    threads: dict[str, dict[str, Any]] = {}
    for email in emails:
        key = key_of(email)
        thread = threads.get(key)
        if thread is None:
            thread = threads[key] = {"id": _thread_id(key), "messages": []}
        thread["messages"].append(email)

    result = []
    for thread in threads.values():
        messages = sorted(thread["messages"], key=lambda e: str(e["sent_at"] or ""))
        last = messages[-1]
        senders: list[str] = []
        for email in reversed(messages):
            name = sender_name(email["from"])
            if name not in senders:
                senders.append(name)
        result.append(
            {
                "id": thread["id"],
                "subject": next((e["subject"] for e in messages if e["subject"]), "")
                or "(no subject)",
                "account": last["account"],
                "participants": senders[:4],
                "last_at": last["sent_at"],
                "preview": re.sub(r"\s+", " ", last["text"]).strip()[:140] or None,
                "messages": messages,
            }
        )
    result.sort(key=lambda t: str(t["last_at"] or ""), reverse=True)
    return result


def list_threads(user_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
    return group_threads(list_email(user_id, limit=limit))
