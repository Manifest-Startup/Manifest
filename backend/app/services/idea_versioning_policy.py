"""
Product rules for Google Docs–style idea version history:

- **manual**: User clicked "Save Version" (named checkpoint).
- **auto**: Created after user-driven edits when content changed and the min interval
  since the last **auto** version has elapsed; duplicates (same content hash as latest
  version) are skipped.
- **system**: Restore flow and similar; not shown as a user "checkpoint" in the same sense.

Background AI document writes (`_update_idea_documents`) do **not** call this module
unless explicitly added later (avoids flooding history).

Env:

- ``AUTO_VERSION_MIN_INTERVAL_SECONDS`` — min seconds between **auto** snapshots (default 90).
- ``AUTO_VERSION_MAX_AUTO_PER_IDEA`` — max **auto** rows to keep per idea; oldest auto rows
  are deleted after each new auto insert when over limit (0 = unlimited).
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

VERSION_SNAPSHOT_FIELDS = (
    "title",
    "description",
    "business_model_canvas",
    "pitch_deck",
    "product_requirements_document",
    "provisional_patent",
)

VERSION_KIND_MANUAL = "manual"
VERSION_KIND_AUTO = "auto"
VERSION_KIND_SYSTEM = "system"


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def auto_version_min_interval_seconds() -> int:
    return max(1, _int_env("AUTO_VERSION_MIN_INTERVAL_SECONDS", 90))


def auto_version_max_auto_per_idea() -> int:
    """0 means no automatic pruning."""
    return max(0, _int_env("AUTO_VERSION_MAX_AUTO_PER_IDEA", 100))


def snapshot_payload_from_idea(idea: dict[str, Any]) -> str:
    payload = {k: idea.get(k) for k in VERSION_SNAPSHOT_FIELDS}
    return json.dumps(payload, sort_keys=True, default=str)


def compute_content_hash(idea: dict[str, Any]) -> str:
    return hashlib.sha256(snapshot_payload_from_idea(idea).encode("utf-8")).hexdigest()


def compute_content_hash_from_version_row(version_row: dict[str, Any]) -> str:
    return compute_content_hash({k: version_row.get(k) for k in VERSION_SNAPSHOT_FIELDS})
