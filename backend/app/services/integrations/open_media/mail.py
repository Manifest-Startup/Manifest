"""Email from the person's own mailbox, through Open Media (``/v1/connected/me/mailboxes`` and
``/v1/connected/me/email``).

Open Media holds the mailbox and its credentials; Manifest never sees them. A send carries an
``Idempotency-Key`` (the goal step's id), and Open Media derives the Message-ID from it, so a
retried send answers with the stored copy instead of emailing anyone twice. The sent copy is
stored in the person's mail, so the conversation and any reply show up in Messages.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from app.services.integrations.open_media.client import get_client

EMAIL = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[a-z]{2,}$", re.IGNORECASE)
MAX_SUBJECT_CHARS = 200
MAX_BODY_CHARS = 20_000


def is_email(value: Any) -> bool:
    return isinstance(value, str) and bool(EMAIL.match(value.strip()))


def mailboxes(user_id: str) -> list[dict[str, Any]]:
    body = get_client().connected(user_id, "GET", "/mailboxes")
    return [m for m in body.get("mailboxes") or [] if isinstance(m, dict)]


def sending_mailbox(user_id: str) -> dict[str, Any] | None:
    """The mailbox a new email would go from: the first connected one that can send."""
    boxes = mailboxes(user_id)
    return next(
        (m for m in boxes if m.get("can_send") and m.get("status") == "connected"),
        next((m for m in boxes if m.get("can_send")), None),
    )


def send(
    user_id: str,
    *,
    to: str,
    subject: str,
    text: str,
    idempotency_key: str,
    mailbox_id: str | None = None,
) -> dict[str, Any]:
    """Send one new email. Returns ``{mailbox_id, from, message, replayed?}``."""
    if not is_email(to):
        raise ValueError("That isn't an email address.")
    subject = " ".join((subject or "").split())
    if not subject or len(subject) > MAX_SUBJECT_CHARS:
        raise ValueError(f"Give the email a subject of up to {MAX_SUBJECT_CHARS} characters.")
    text = (text or "").strip()
    if not text or len(text) > MAX_BODY_CHARS:
        raise ValueError(f"Emails can be up to {MAX_BODY_CHARS:,} characters.")
    payload: dict[str, Any] = {"to": [to.strip()], "subject": subject, "text": text}
    if mailbox_id:
        payload["mailbox_id"] = mailbox_id
    return get_client().connected(
        user_id,
        "POST",
        "/email",
        json=payload,
        headers={"Idempotency-Key": idempotency_key},
        idempotent=True,
    )


def stored(user_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
    """The person's stored email, newest first: ``{mailboxId, folder, from, to, subject, text,
    sentAt, messageId, inReplyTo}`` (Open Media's ``/v1/me/email``)."""
    body = get_client().connected(user_id, "GET", "/email", params={"limit": limit})
    return [r for r in body.get("data") or [] if isinstance(r, dict)]


def sync(user_id: str, mailbox_id: str) -> None:
    """Fetch new mail into a mailbox now; Open Media otherwise fetches only while its app is open."""
    get_client().connected(
        user_id, "POST", f"/mailboxes/{quote(str(mailbox_id), safe='')}/sync", idempotent=True
    )
