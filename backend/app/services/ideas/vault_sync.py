"""Your vault, synced to your account like iCloud Drive or OneDrive (ADR 0007).

The Manifest-written part of the vault comes from ``vault.build_vault``. This module stores the
person's own part, so every computer they sign in on sees the same vault:

- their files outside ``Manifest/`` (``Notes/…`` and anything else they create), and
- their writing around the generated block in ``Manifest/`` files (the "overlay").

Each file is one row keyed by ``(user_id, path)`` with a SHA-256 of its content. A write names
the hash it was based on; if the account has moved on since, the write is refused as a conflict
and the client keeps both versions (a "conflicted copy", as Dropbox and OneDrive do). Deletes are
tombstones, so other computers learn about them; clients move the file to the vault's ``.trash``.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

TABLE = "vault_files"
MAX_BYTES = 512 * 1024
MAX_FILES = 5000
MAX_PATH = 400
PAGE = 500
EXTENSIONS = (".md", ".txt", ".canvas")
_BAD_SEGMENT = re.compile(r'[\x00-\x1f\\:*?"<>|]')
COLUMNS = "path, content, sha256, deleted, device, updated_at"


class VaultSyncError(ValueError):
    """The request can't be stored (bad path, too large, too many files)."""


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    return str(value)


def clean_path(path: str) -> str:
    """A vault-relative POSIX path the person may sync, or ``VaultSyncError``."""
    raw = str(path or "").replace("\\", "/").strip()
    parts = raw.split("/")
    if not raw or raw.startswith("/") or len(raw) > MAX_PATH:
        raise VaultSyncError("Use a path inside the vault, like Notes/My idea.md.")
    for part in parts:
        if part in ("", ".", "..") or part.startswith(".") or _BAD_SEGMENT.search(part):
            raise VaultSyncError(f"'{raw}' isn't a vault path Manifest can sync.")
    if not raw.lower().endswith(EXTENSIONS):
        raise VaultSyncError("Only Markdown, text and canvas files sync (.md, .txt, .canvas).")
    return raw


def _public(row: dict[str, Any]) -> dict[str, Any]:
    deleted = bool(row.get("deleted"))
    return {
        "path": row["path"],
        "content": None if deleted else row.get("content") or "",
        "sha256": row.get("sha256") or "",
        "deleted": deleted,
        "device": row.get("device"),
        "updated_at": _iso(row.get("updated_at")),
    }


def list_files(db: Any, user_id: str, since: str | None = None) -> dict[str, Any]:
    """Files changed after ``since`` (all of them, with tombstones, when it's empty).

    ``server_time`` is read before the query; clients pass it back as ``since`` (minus a small
    overlap, because applying a row twice is harmless) to page forward."""
    server_time = datetime.now(UTC).isoformat()
    query = db.table(TABLE).select(COLUMNS).eq("user_id", user_id)
    if since:
        query = query.gt("updated_at", since)
    rows = query.order("updated_at").limit(MAX_FILES).execute().data or []
    return {"server_time": server_time, "files": [_public(r) for r in rows]}


def _current(db: Any, user_id: str, path: str) -> dict[str, Any] | None:
    rows = (
        db.table(TABLE).select(COLUMNS).eq("user_id", user_id).eq("path", path).execute().data or []
    )
    return rows[0] if rows else None


def _precheck(current: dict[str, Any] | None, content: str | None, base: str | None) -> str | None:
    """ "unchanged" or "conflict" when nothing should be written; None to go ahead."""
    live = current is not None and not current.get("deleted")
    live_sha = (current or {}).get("sha256") or ""
    if content is None:
        if not live:
            return "unchanged"
        return "conflict" if live_sha != base else None
    if live and live_sha == sha256(content):
        return "unchanged"
    if live and live_sha != base:
        return "conflict"
    return None


def _check_quota(db: Any, user_id: str) -> None:
    rows = db.table(TABLE).select("path").eq("user_id", user_id).limit(MAX_FILES).execute().data
    if len(rows or []) >= MAX_FILES:
        raise VaultSyncError(f"Your vault already syncs {MAX_FILES} files.")


def put_file(
    db: Any,
    user_id: str,
    path: str,
    content: str | None,
    base_sha256: str | None,
    *,
    device: str | None = None,
) -> dict[str, Any]:
    """Save (``content``) or delete (``content=None``) one file.

    ``base_sha256`` is the hash this computer last synced for the path (empty for a new file).
    Returns ``{"status": "saved" | "unchanged" | "conflict", "file": <account's version>}``."""
    path = clean_path(path)
    if content is not None and len(content.encode("utf-8")) > MAX_BYTES:
        raise VaultSyncError(f"'{path}' is over {MAX_BYTES // 1024} KB; it stays on this computer.")
    current = _current(db, user_id, path)
    early = _precheck(current, content, base_sha256 or None)
    if early is not None:
        return {"status": early, "file": _public(current) if current else None}
    if current is None:
        _check_quota(db, user_id)

    row = {
        "content": "" if content is None else content,
        "sha256": "" if content is None else sha256(content),
        "deleted": content is None,
        "device": (device or "")[:120] or None,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if current is None:
        try:
            saved = db.table(TABLE).insert({"user_id": user_id, "path": path, **row}).execute().data
        except Exception:  # unique (user_id, path): another computer created it first
            latest = _current(db, user_id, path)
            if latest is None:
                raise
            return {"status": "conflict", "file": _public(latest)}
        return {"status": "saved", "file": _public(saved or {"path": path, **row})}

    # Compare-and-swap on the hash we read, so two computers can't both win.
    saved = (
        db.table(TABLE)
        .update(row)
        .eq("user_id", user_id)
        .eq("path", path)
        .eq("sha256", current.get("sha256") or "")
        .execute()
        .data
    )
    if not saved:
        latest = _current(db, user_id, path)
        return {"status": "conflict", "file": _public(latest) if latest else None}
    return {"status": "saved", "file": _public(saved[0] if isinstance(saved, list) else saved)}
