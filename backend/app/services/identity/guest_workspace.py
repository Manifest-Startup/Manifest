"""Guest try-before-signup: rate limits, merge workspace, and full-account checks."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.utils.logger import logger

try:
    from psycopg2 import errors as _pg_errors  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    _pg_errors = None  # type: ignore

_UndefinedTable = getattr(_pg_errors, "UndefinedTable", None) if _pg_errors else None

if TYPE_CHECKING:
    pass

# Simple in-process rate limit for start_guest_session (IP -> list of epoch seconds).
_guest_start_timestamps: dict[str, list[float]] = {}
_GUEST_START_LIMIT = 15
_GUEST_START_WINDOW_SEC = 3600


def check_guest_start_rate_limit(client_host: str | None) -> None:
    """Raise Exception if this IP has exceeded guest session starts per hour."""
    ip = (client_host or "unknown").strip() or "unknown"
    now = time.time()
    window_start = now - _GUEST_START_WINDOW_SEC
    bucket = _guest_start_timestamps.setdefault(ip, [])
    while bucket and bucket[0] < window_start:
        bucket.pop(0)
    if len(bucket) >= _GUEST_START_LIMIT:
        logger.warning("[guest] Rate limit exceeded for IP %s", ip)
        raise Exception("Too many guest sessions from this network. Please try again later.")
    bucket.append(now)


def fetch_user_is_guest(db, user_id: str) -> bool:
    try:
        r = db.table("users").select("is_guest").eq("user_id", user_id).single().execute()
        if not r.data:
            return False
        return bool(r.data.get("is_guest"))
    except Exception as exc:
        logger.warning("[guest] is_guest lookup failed for %s: %s", user_id, exc)
        return False


def claim_guest_workspace(target_user_id: str, guest_user_id: str) -> int:
    """Merge the guest workspace the browser is signed in to into ``target_user_id``.

    Used by the Open Media sign-in callback: the guest's own session cookie proves
    ownership, so the stored merge secret is read here instead of from the client.
    Idempotent: a guest that was already claimed (a retried callback) merges 0 ideas.
    """
    from app.db.database import get_db_connection

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT is_guest, guest_merge_secret FROM users WHERE user_id = %s",
            (guest_user_id,),
        )
        row = cur.fetchone()
        if not row or not row.get("is_guest") or not row.get("guest_merge_secret"):
            return 0
        moved = merge_guest_workspace_sql(
            cur, target_user_id, guest_user_id, str(row["guest_merge_secret"])
        )
        conn.commit()
    return moved


def merge_guest_workspace_sql(  # noqa: C901
    cur, target_user_id: str, guest_user_id: str, merge_secret: str
) -> int:
    """
    Verify guest + secret, reassign workspace rows from guest to target, clear guest flags.
    Returns number of ideas transferred.
    """
    cur.execute(
        """
        SELECT is_guest, guest_merge_secret, guest_expires_at
        FROM users
        WHERE user_id = %s
        FOR UPDATE
        """,
        (guest_user_id,),
    )
    row = cur.fetchone()
    if not row:
        raise Exception("Guest account not found")
    is_guest = row.get("is_guest") if isinstance(row, dict) else row["is_guest"]
    if not is_guest:
        raise Exception("This workspace has already been claimed or is not a guest account")
    stored_secret = (
        row.get("guest_merge_secret") if isinstance(row, dict) else row["guest_merge_secret"]
    )
    if not stored_secret or stored_secret != merge_secret:
        raise Exception("Invalid or expired merge secret")
    expires = row.get("guest_expires_at") if isinstance(row, dict) else row.get("guest_expires_at")
    if expires is not None:
        exp = expires
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise Exception("Guest session has expired. Please start a new try session.")

    if target_user_id == guest_user_id:
        raise Exception("Cannot merge a guest workspace into itself")

    cur.execute("SELECT is_guest FROM users WHERE user_id = %s FOR UPDATE", (target_user_id,))
    trow = cur.fetchone()
    if not trow:
        raise Exception("Account not found")
    target_is_guest = trow.get("is_guest") if isinstance(trow, dict) else trow["is_guest"]
    if target_is_guest:
        raise Exception("Sign in with a full account to claim this guest workspace")

    # Optional tables: ignore if missing (older DBs).
    def _run(sql: str, params: tuple[Any, ...]) -> None:
        try:
            cur.execute(sql, params)
        except Exception as exc:
            if _UndefinedTable is not None and isinstance(exc, _UndefinedTable):
                logger.info("[guest] Skipping optional merge SQL (table missing): %s", sql[:60])
                return
            msg = str(exc).lower()
            if "undefinedtable" in msg or "does not exist" in msg:
                logger.info("[guest] Skipping optional merge SQL (table missing): %s", sql[:60])
                return
            raise

    uid_pair = (target_user_id, guest_user_id)

    _run("UPDATE pitch_decks SET user_id = %s WHERE user_id = %s", uid_pair)
    _run("UPDATE intellectual_properties SET user_id = %s WHERE user_id = %s", uid_pair)
    _run("UPDATE product_requirements_documents SET user_id = %s WHERE user_id = %s", uid_pair)
    _run("UPDATE comments SET user_id = %s WHERE user_id = %s", uid_pair)
    _run("UPDATE companies SET user_id = %s WHERE user_id = %s", uid_pair)
    _run("UPDATE integrations SET user_id = %s WHERE user_id = %s", uid_pair)
    _run("UPDATE pitch_reels SET creator_user_id = %s WHERE creator_user_id = %s", uid_pair)
    _run("UPDATE idea_votes SET user_id = %s WHERE user_id = %s", uid_pair)
    _run("UPDATE idea_collaborators SET user_id = %s WHERE user_id = %s", uid_pair)
    _run("UPDATE idea_versions SET created_by = %s WHERE created_by = %s", uid_pair)

    cur.execute("UPDATE ideas SET user_id = %s WHERE user_id = %s RETURNING idea_id", uid_pair)
    moved = cur.fetchall() or []
    idea_count = len(moved)

    cur.execute(
        """
        UPDATE users
        SET is_guest = FALSE,
            guest_merge_secret = NULL,
            guest_expires_at = NULL
        WHERE user_id = %s
        """,
        (guest_user_id,),
    )

    return idea_count
