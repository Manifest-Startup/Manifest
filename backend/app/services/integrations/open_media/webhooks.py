"""Signed webhooks from Open Media (``POST /api/webhooks/open-media``).

Headers: ``X-Open-Media-Event``, ``X-Open-Media-Delivery``,
``X-Open-Media-Timestamp`` (unix seconds) and ``X-Open-Media-Signature:
sha256=<hex HMAC-SHA256(secret, timestamp + "." + raw_body)>``.

Bodies carry IDs only (never message text). Manifest uses them to drop cached
unread counts and clip stats, so badges and counts refresh on the next read.
Deliveries older than 5 minutes are rejected and repeated delivery ids are
ignored (Open Media retries with backoff).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from app.services.integrations.open_media import settings
from app.services.integrations.open_media.clips import invalidate_clip_stats
from app.services.integrations.open_media.messaging import invalidate_unread
from app.services.shared.cache import cache_get, cache_set
from app.utils.logger import logger

MAX_AGE_SECONDS = 300
DEDUPE_TTL_SECONDS = 24 * 3600  # Open Media gives up retrying after about a day
MESSAGE_EVENTS = {"message.created", "conversation.read"}
POST_EVENTS = {"post.liked", "post.commented", "post.deleted"}


class WebhookRejected(ValueError):
    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


def sign(secret: str, timestamp: str, raw_body: bytes) -> str:
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + raw_body, hashlib.sha256)
    return f"sha256={digest.hexdigest()}"


def verify(
    raw_body: bytes, *, timestamp: str | None, signature: str | None, now: float | None = None
) -> None:
    secret = settings.webhook_secret()
    if not secret:
        raise WebhookRejected("Open Media webhooks are not configured.", status=503)
    if not timestamp or not signature:
        raise WebhookRejected("Missing signature headers.")
    try:
        sent_at = int(timestamp)
    except ValueError:
        raise WebhookRejected("Invalid timestamp.") from None
    current = time.time() if now is None else now
    if abs(current - sent_at) > MAX_AGE_SECONDS:
        raise WebhookRejected("Stale delivery.")
    if not hmac.compare_digest(sign(secret, timestamp, raw_body), signature.strip()):
        raise WebhookRejected("Bad signature.")


def _seen(delivery_id: str) -> bool:
    key = f"open_media:webhook:{delivery_id}"
    if cache_get(key):
        return True
    cache_set(key, True, DEDUPE_TTL_SECONDS)
    return False


def handle(
    raw_body: bytes,
    *,
    event: str | None,
    timestamp: str | None,
    signature: str | None,
    now: float | None = None,
) -> dict[str, Any]:
    """Verify and apply one delivery. Returns ``{"ok": True, "duplicate"?: True}``."""
    verify(raw_body, timestamp=timestamp, signature=signature, now=now)
    try:
        payload = json.loads(raw_body or b"{}")
    except ValueError:
        raise WebhookRejected("Body is not JSON.", status=400) from None
    if not isinstance(payload, dict) or not payload.get("id"):
        raise WebhookRejected("Missing delivery id.", status=400)
    if _seen(str(payload["id"])):
        return {"ok": True, "duplicate": True}

    kind = str(payload.get("type") or event or "")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if kind in MESSAGE_EVENTS:
        recipients = [str(r) for r in data.get("recipient_ids") or [] if r]
        actor = data.get("actor_id")
        invalidate_unread(recipients + ([str(actor)] if actor else []))
    elif kind in POST_EVENTS:
        invalidate_clip_stats([str(data["post_id"])] if data.get("post_id") else None)
    logger.info(
        "[open_media] webhook applied",
        extra={"open_media.event": kind, "open_media.delivery": str(payload["id"])},
    )
    return {"ok": True}
