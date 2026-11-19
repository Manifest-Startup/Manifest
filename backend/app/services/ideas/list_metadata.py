"""Denormalized metadata and pagination helpers for the workspace ideas list.

Stage #3 of the backend migration (#215): keep ``ideas`` list queries from
reading multi-MB generated document blobs on every dashboard load.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

IDEA_SUMMARY_DB_COLUMNS = (
    "idea_id, user_id, title, created_at, updated_at, is_published, "
    "generated_asset_count, has_description"
)

IDEA_LIST_METADATA_SOURCE_COLUMNS = (
    "description, pitch_deck, product_requirements_document, "
    "provisional_patent, business_model_canvas"
)

_GENERATED_ASSET_KEYS = (
    "pitch_deck",
    "product_requirements_document",
    "provisional_patent",
    "business_model_canvas",
)


def generated_asset_count_from_row(idea_data: dict[str, object]) -> int:
    n = 0
    for key in _GENERATED_ASSET_KEYS:
        val = idea_data.get(key)
        if val is not None and str(val).strip():
            n += 1
    return n


def compute_idea_list_metadata(row: dict[str, object]) -> dict[str, object]:
    return {
        "generated_asset_count": generated_asset_count_from_row(row),
        "has_description": bool(str(row.get("description") or "").strip()),
    }


def refresh_idea_list_metadata(db, idea_id: str, user_id: str | None) -> None:
    """Recompute denormalized list columns after a document or description write."""
    if not user_id:
        return

    row_resp = (
        db.table("ideas")
        .select(IDEA_LIST_METADATA_SOURCE_COLUMNS)
        .eq("idea_id", idea_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not row_resp.data:
        return

    meta = compute_idea_list_metadata(row_resp.data)
    db.table("ideas").update(meta).eq("idea_id", idea_id).eq("user_id", user_id).execute()


def encode_ideas_cursor(created_at: datetime, idea_id: str) -> str:
    payload = {"c": created_at.isoformat(), "i": idea_id}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_ideas_cursor(raw: str) -> tuple[datetime, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
        created_at = datetime.fromisoformat(str(payload["c"]))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at, str(payload["i"])
    except Exception as exc:
        raise ValueError("Invalid ideas cursor") from exc


def normalize_ideas_page_size(first: int, *, default: int = 100, maximum: int = 200) -> int:
    try:
        value = int(first)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


def read_list_metadata(row: dict[str, Any]) -> tuple[int, bool]:
    gac = row.get("generated_asset_count")
    if gac is None:
        gac = generated_asset_count_from_row(row)
    has_desc = row.get("has_description")
    if has_desc is None:
        has_desc = bool(str(row.get("description") or "").strip())
    return int(gac), bool(has_desc)
