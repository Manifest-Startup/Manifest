"""Step-up authentication — short-lived "I just re-authenticated" proofs.

Used by sensitive endpoints (admin actions, MFA reset, SSO config changes,
API key creation in some flows) so a stolen long-lived session cookie is
not enough to perform destructive operations on its own.

Verification methods supported:
- ``password`` — user re-types current password
- ``totp`` — user enters current TOTP code
- ``webauthn`` — user completes a passkey assertion (when wired in)

A successful verification inserts a row into ``step_up_verifications``
with a configurable TTL (default 5 minutes). The route dependency
``require_recent_auth(...)`` rejects requests without an active row for
the current session.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.db.database import get_db_connection
from app.routes.dependencies import require_user_id
from app.utils.auth_utils import get_current_session_id_optional
from app.utils.logger import logger
from fastapi import Depends, HTTPException, Request

DEFAULT_TTL_SECONDS = 300  # 5 minutes
MAX_TTL_SECONDS = 30 * 60  # 30 minutes


def _now() -> datetime:
    return datetime.now(timezone.utc)


def record_step_up(
    user_id: str,
    *,
    session_id: str | None,
    method: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    request_ip: str | None = None,
    user_agent: str | None = None,
) -> str | None:
    """Persist a recent re-auth proof. Returns the verification ID or None on error."""
    ttl = max(60, min(ttl_seconds, MAX_TTL_SECONDS))
    verification_id = str(uuid.uuid4())
    expires_at = _now() + timedelta(seconds=ttl)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO step_up_verifications
                        (id, user_id, session_id, method, expires_at, request_ip, user_agent)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        verification_id,
                        user_id,
                        session_id,
                        method,
                        expires_at,
                        request_ip,
                        user_agent,
                    ),
                )
            conn.commit()
        return verification_id
    except Exception as exc:
        logger.warning("[step_up] record failed for %s: %s", user_id, exc)
        return None


def has_recent_step_up(
    user_id: str, session_id: str | None, *, max_age_seconds: int = DEFAULT_TTL_SECONDS
) -> bool:
    if not user_id:
        return False
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT 1 FROM step_up_verifications
                    WHERE user_id = %s
                      AND revoked_at IS NULL
                      AND expires_at > NOW()
                      AND verified_at > NOW() - (%s || ' seconds')::interval
                      AND (session_id IS NULL OR session_id::text = %s OR %s IS NULL)
                    LIMIT 1
                    """,
                (user_id, str(max_age_seconds), session_id, session_id),
            )
            return cur.fetchone() is not None
    except Exception as exc:
        logger.warning("[step_up] lookup failed for %s: %s", user_id, exc)
        return False


def revoke_step_up_for_session(session_id: str) -> None:
    if not session_id:
        return
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE step_up_verifications SET revoked_at = NOW() "
                    "WHERE session_id::text = %s AND revoked_at IS NULL",
                    (session_id,),
                )
            conn.commit()
    except Exception as exc:
        logger.debug("[step_up] revoke failed for session %s: %s", session_id, exc)


def _recent_login_satisfies(request: Request, max_age_seconds: int) -> bool:
    """Return True if the active session JWT was minted within the window.

    The session token carries an ``auth_iat`` claim recording the moment
    the user actually presented credentials (password / SSO / MFA). A
    fresh login implicitly satisfies the "recent auth" requirement, so
    the user does not have to re-prove a second time within the same
    short window. Step-up is still required outside that window.
    """
    try:
        token = request.cookies.get("session_token") if request else None
        if not token:
            auth = request.headers.get("authorization") if request else None
            if auth and auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1].strip()
        if not token:
            return False
        from app.auth.replit_auth import decode_session_token

        payload = decode_session_token(token) or {}
        auth_iat = int(payload.get("auth_iat") or 0)
        if auth_iat <= 0:
            return False
        age = _now().timestamp() - auth_iat
        return 0 <= age <= max_age_seconds
    except Exception as exc:
        logger.debug("[step_up] auth_iat check skipped: %s", exc)
        return False


def require_recent_auth(max_age_seconds: int = DEFAULT_TTL_SECONDS) -> Callable:
    """Return a FastAPI dependency that requires a recent re-auth proof.

    Two paths are accepted (SEC-026):
    1. ``auth_iat`` claim on the current session JWT is within
       ``max_age_seconds`` of now (i.e. the user just logged in).
    2. A live row in ``step_up_verifications`` for this user/session.

    Either is sufficient. This avoids forcing a step-up immediately after
    a successful login while still demanding fresh proof for sessions
    that have been alive longer than the window.
    """

    def _dep(
        request: Request,
        user_id: str = Depends(require_user_id),
    ) -> str:
        if _recent_login_satisfies(request, max_age_seconds):
            return user_id
        session_id = get_current_session_id_optional(request)
        if not has_recent_step_up(user_id, session_id, max_age_seconds=max_age_seconds):
            raise HTTPException(
                status_code=401,
                detail="Re-authentication required",
                headers={"X-Step-Up-Required": "1"},
            )
        return user_id

    return _dep
