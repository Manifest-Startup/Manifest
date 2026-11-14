"""Password history — prevent reuse of the last N passwords.

Stores bcrypt hashes (NEVER plaintext) in ``password_history`` and
verifies any new candidate against the most recent entries.
"""

from __future__ import annotations

from app.db.database import get_db_connection
from app.security.passwords import hash_password, verify_password
from app.utils.logger import logger

HISTORY_DEPTH = 5


def record_password(user_id: str, password_hash: str) -> None:
    """Append the freshly-set password hash to the user's history.

    Older entries past ``HISTORY_DEPTH`` are pruned so we never keep a
    forever-growing pile of bcrypt hashes per user.
    """
    if not user_id or not password_hash:
        return
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO password_history (user_id, password_hash) VALUES (%s, %s)",
                    (user_id, password_hash),
                )
                cur.execute(
                    """
                    DELETE FROM password_history
                    WHERE user_id = %s
                      AND id NOT IN (
                          SELECT id FROM password_history
                          WHERE user_id = %s
                          ORDER BY created_at DESC
                          LIMIT %s
                      )
                    """,
                    (user_id, user_id, HISTORY_DEPTH),
                )
            conn.commit()
    except Exception as exc:
        # Non-fatal: don't block a password change because history table is missing.
        logger.warning("[pwd_history] record failed for %s: %s", user_id, exc)


def is_recent_reuse(user_id: str, candidate_password: str) -> bool:
    """Return True if ``candidate_password`` matches any recent stored hash."""
    if not user_id or not candidate_password:
        return False
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT password_hash FROM password_history
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                (user_id, HISTORY_DEPTH),
            )
            rows = cur.fetchall() or []
        hashes: list[str] = [r["password_hash"] for r in rows if r.get("password_hash")]
    except Exception as exc:
        logger.warning("[pwd_history] lookup failed for %s: %s", user_id, exc)
        return False
    for old_hash in hashes:
        try:
            if verify_password(candidate_password, old_hash):
                return True
        except Exception:
            continue
    return False


# Re-exported for callers wiring history into existing reset/signup flows.
__all__ = ["record_password", "is_recent_reuse", "hash_password", "HISTORY_DEPTH"]
