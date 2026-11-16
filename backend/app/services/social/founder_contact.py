"""Who can message an idea's founder, and how ("Message founder").

Messages themselves live in Open Media; this module only answers the Manifest
questions: is the idea published, who owns it, and has that founder linked an
Open Media account (their handle is the address a conversation is opened with).
"""

from __future__ import annotations

from typing import Any

from app.services.integrations.open_media import identity
from app.utils.logger import logger

FOUNDER_NOT_LINKED_MESSAGE = (
    "This founder hasn't connected Open Media yet, so they can't receive messages."
)


def _idea(db, idea_id: str) -> dict[str, Any] | None:
    response = (
        db.table("ideas")
        .select("idea_id, user_id, title, is_published")
        .eq("idea_id", idea_id)
        .single()
        .execute()
    )
    return response.data if isinstance(response.data, dict) else None


def get_idea_owner(db, idea_id: str, viewer_user_id: str) -> dict[str, Any] | None:
    """Founder card data for an idea, including whether the viewer can message them."""
    try:
        idea = _idea(db, idea_id)
        if not idea:
            return None
        owner_id = str(idea.get("user_id") or "")
        user_response = (
            db.table("users")
            .select("user_id, username, first_name, last_name, bio, profile_picture_url")
            .eq("user_id", owner_id)
            .single()
            .execute()
        )
        owner = user_response.data if isinstance(user_response.data, dict) else None
        if not owner:
            return None
    except Exception as exc:
        logger.error("[founder_contact] idea owner lookup failed: %s", type(exc).__name__)
        return None

    is_published = bool(idea.get("is_published"))
    is_owner = str(viewer_user_id or "") == owner_id
    handle = identity.handle_for_user(owner_id)
    return {
        "idea_id": idea_id,
        "idea_title": idea.get("title"),
        "owner": owner,
        "is_published": is_published,
        "open_media_handle": handle,
        "can_message": (not is_owner) and is_published and bool(handle),
    }


def founder_handle_for_idea(db, idea_id: str, requester_user_id: str) -> tuple[str, str | None]:
    """``(founder_handle, idea_title)`` for "Message founder", or ``ValueError`` with a clear reason."""
    idea = _idea(db, idea_id)
    if not idea:
        raise ValueError("Idea not found.")
    owner_id = str(idea.get("user_id") or "")
    if owner_id == str(requester_user_id):
        raise ValueError("You can't message yourself about your own idea.")
    if not idea.get("is_published"):
        raise ValueError("Messaging is only available for published ideas")
    handle = identity.handle_for_user(owner_id)
    if not handle:
        raise ValueError(FOUNDER_NOT_LINKED_MESSAGE)
    return handle, idea.get("title")
