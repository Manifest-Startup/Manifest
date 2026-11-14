"""Guest-to-full-account upgrade via emailed one-time link (voice-friendly onboarding)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.database import get_db_connection
from app.services.guest_workspace_service import fetch_user_is_guest
from app.utils.logger import logger
from app.utils.reset_token_utils import generate_reset_token, hash_token

GUEST_UPGRADE_TOKEN_TTL_MINUTES = 60


def build_guest_upgrade_url(raw_token: str) -> str:
    """Public claim URL; host from APP_BASE_URL only (same rule as password reset)."""
    base = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    if not base:
        logger.warning(
            "[guest_upgrade] APP_BASE_URL not set; upgrade link will use localhost. "
            "Set APP_BASE_URL for production email links."
        )
        base = "http://localhost:5000"
    return f"{base}/auth?guest_upgrade_token={raw_token}"


def create_guest_upgrade_token(
    *,
    user_id: str,
    email: str,
    db_executor,
) -> str | None:
    """Create a one-time token row; return raw token for email, or None on failure."""

    normalised = (email or "").lower().strip()
    if not normalised or "@" not in normalised:
        logger.warning("[guest_upgrade] invalid email for user_id=%s", user_id)
        return None

    if not fetch_user_is_guest(db_executor, user_id):
        logger.warning("[guest_upgrade] not a guest user_id=%s", user_id)
        return None

    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT user_id FROM users
                    WHERE email = %s AND user_id <> %s AND COALESCE(is_guest, FALSE) = FALSE
                    """,
                (normalised, user_id),
            )
            if cur.fetchone():
                logger.info(
                    "[guest_upgrade] email already registered; skipping token for guest %s",
                    user_id,
                )
                return None

            cur.execute(
                """
                    UPDATE guest_upgrade_tokens SET used_at = NOW()
                    WHERE user_id = %s AND used_at IS NULL
                    """,
                (user_id,),
            )

            raw_token, token_hash = generate_reset_token()
            expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=GUEST_UPGRADE_TOKEN_TTL_MINUTES
            )

            cur.execute(
                """
                    INSERT INTO guest_upgrade_tokens (user_id, email, token_hash, expires_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                (user_id, normalised, token_hash, expires_at),
            )
        return raw_token
    except Exception as exc:
        logger.error("[guest_upgrade] failed to create token for %s: %s", user_id, exc)
        return None


def complete_guest_upgrade(  # noqa: C901
    raw_token: str, password: str, request_ip: str | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate token + password policy; upgrade guest row. Returns (payload_dict, error_message)."""

    from app.services.password_reset_service import (
        check_guest_upgrade_attempt_rate_limit,
        validate_password_for_user,
    )
    from app.utils.password_utils import hash_password

    if not check_guest_upgrade_attempt_rate_limit(request_ip):
        return None, "Too many attempts. Try again later."

    cleaned = (raw_token or "").strip()
    if not cleaned:
        return None, "Invalid or expired link."

    validation_error = validate_password_for_user(password, user_id=None)
    if validation_error:
        return None, validation_error

    token_hash = hash_token(cleaned)

    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT id, user_id, email, expires_at, used_at
                    FROM guest_upgrade_tokens
                    WHERE token_hash = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                (token_hash,),
            )
            row = cur.fetchone()
            if not row:
                return None, "Invalid or expired link."

            def _col(name: str) -> Any:
                return row.get(name) if isinstance(row, dict) else row[name]

            if _col("used_at") is not None:
                return None, "This link was already used."

            exp = _col("expires_at")
            if isinstance(exp, str):
                exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                return None, "This link has expired."

            uid = str(_col("user_id"))
            new_email = str(_col("email"))
            token_id = _col("id")

            cur.execute(
                """
                    SELECT user_id, COALESCE(is_guest, FALSE) AS is_guest
                    FROM users WHERE user_id = %s FOR UPDATE
                    """,
                (uid,),
            )
            urow = cur.fetchone()
            if not urow:
                return None, "Account not found."
            ug = urow.get("is_guest") if isinstance(urow, dict) else urow[1]
            if not ug:
                return None, "This workspace is already a full account."

            cur.execute(
                """
                    SELECT user_id FROM users
                    WHERE email = %s AND user_id <> %s
                    """,
                (new_email, uid),
            )
            if cur.fetchone():
                return None, "That email is already registered. Sign in instead."

            password_hash = hash_password(password)

            cur.execute(
                """
                    UPDATE users SET
                        email = %s,
                        password_hash = %s,
                        is_guest = FALSE,
                        guest_merge_secret = NULL,
                        guest_expires_at = NULL,
                        auth_provider = 'email'
                    WHERE user_id = %s
                    """,
                (new_email, password_hash, uid),
            )

            cur.execute(
                """
                    UPDATE guest_upgrade_tokens SET used_at = NOW()
                    WHERE id = %s
                    """,
                (token_id,),
            )

            try:
                from app.security.password_history import record_password

                record_password(uid, password_hash)
            except Exception:
                pass

        return {"user_id": uid, "email": new_email}, None
    except Exception as exc:
        logger.error("[guest_upgrade] complete failed: %s", exc)
        return None, "Could not complete upgrade. Try again or sign up from the home page."
