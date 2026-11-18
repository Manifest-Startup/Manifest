import os
import time
import uuid
from datetime import datetime, timedelta, timezone

from app.db.database import get_db_connection
from app.utils.logger import logger
from fastapi import Request

SESSION_TTL_DAYS = 7
# Idle timeout: a session is revoked when it has not been touched for N seconds.
# 24 h matches our SOC 2 commitment for "low-risk operations" sessions.
SESSION_IDLE_TIMEOUT_SECONDS = int(os.getenv("SESSION_IDLE_TIMEOUT_SECONDS", str(24 * 60 * 60)))
# Maximum concurrent active sessions per user. Oldest sessions are revoked
# when a new login pushes the user over this cap.
SESSION_CONCURRENCY_CAP = int(os.getenv("SESSION_CONCURRENCY_CAP", "10"))

# Manifest CLI sessions (ADR 0003) are browser-approved, longer-lived and labelled.
# The label is stored in ``user_agent`` (no schema change) and never overwritten.
CLI_SESSION_LABEL_PREFIX = "Manifest CLI · "
AGENT_SESSION_LABEL_PREFIX = "AI agent · "  # ADR 0004: OAuth-connected agents (MCP)
CLI_SESSION_TTL_DAYS = int(os.getenv("CLI_SESSION_TTL_DAYS", "30"))
CLI_SESSION_IDLE_TIMEOUT_SECONDS = int(
    os.getenv("CLI_SESSION_IDLE_TIMEOUT_SECONDS", str(14 * 24 * 60 * 60))
)


def session_kind(user_agent: object) -> str:
    """``cli`` for a Manifest CLI session, ``agent`` for an AI agent, otherwise ``browser``."""
    if isinstance(user_agent, str) and user_agent.startswith(CLI_SESSION_LABEL_PREFIX):
        return "cli"
    if isinstance(user_agent, str) and user_agent.startswith(AGENT_SESSION_LABEL_PREFIX):
        return "agent"
    return "browser"


def _request_meta(request: Request | None) -> tuple[str | None, str | None]:
    if request is None:
        return None, None
    client = getattr(request, "client", None)
    request_ip = getattr(client, "host", None) if client else None
    user_agent = request.headers.get("user-agent")
    return request_ip, user_agent


def _enforce_concurrency_cap(cur, user_id: str) -> int:
    """Revoke the oldest active sessions until the user is at-or-below the cap."""
    cur.execute(
        """
        SELECT session_id FROM user_sessions
        WHERE user_id = %s AND revoked_at IS NULL AND expires_at > NOW()
        ORDER BY last_seen_at DESC NULLS LAST, created_at DESC
        OFFSET %s
        """,
        (user_id, SESSION_CONCURRENCY_CAP - 1),
    )
    over_cap = cur.fetchall() or []
    if not over_cap:
        return 0
    cur.execute(
        """
        UPDATE user_sessions SET revoked_at = NOW()
        WHERE session_id = ANY(%s::uuid[])
        """,
        ([row["session_id"] for row in over_cap],),
    )
    return cur.rowcount or 0


def create_user_session(
    user_id: str,
    request: Request | None,
    *,
    ttl_days: int = SESSION_TTL_DAYS,
    label: str | None = None,
) -> str:
    """Insert a ``user_sessions`` row. ``label`` replaces the user agent (CLI sessions)."""
    session_id = str(uuid.uuid4())
    request_ip, user_agent = _request_meta(request)
    if label:
        user_agent = label
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_sessions (
                        session_id, user_id, created_at, expires_at, revoked_at,
                        last_seen_at, request_ip, user_agent
                    )
                    VALUES (%s, %s, NOW(), %s, NULL, NOW(), %s, %s)
                    """,
                    (session_id, user_id, expires_at, request_ip, user_agent),
                )
                pruned = _enforce_concurrency_cap(cur, user_id)
                if pruned:
                    logger.info(
                        "[session_service] Pruned %s oldest sessions for user=%s (cap=%s)",
                        pruned,
                        user_id,
                        SESSION_CONCURRENCY_CAP,
                    )
            conn.commit()
    except Exception as exc:
        logger.warning("[session_service] Failed to persist session %s: %s", session_id, exc)
    return session_id


def is_session_active(
    session_id: str, user_id: str, idle_timeout_seconds: int | None = None
) -> bool:
    idle_limit = idle_timeout_seconds or SESSION_IDLE_TIMEOUT_SECONDS
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT last_seen_at, created_at
                    FROM user_sessions
                    WHERE session_id = %s
                      AND user_id = %s
                      AND revoked_at IS NULL
                      AND expires_at > NOW()
                    """,
                (session_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                return False
            # Idle-timeout enforcement (SEC-016).
            last_seen = row.get("last_seen_at") or row.get("created_at")
            if last_seen is not None:
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - last_seen).total_seconds()
                if age > idle_limit:
                    # Auto-revoke the idle session so the next request
                    # also bounces and audit logs reflect the timeout.
                    cur.execute(
                        "UPDATE user_sessions SET revoked_at = NOW() WHERE session_id = %s",
                        (session_id,),
                    )
                    conn.commit()
                    return False
            return True
    except Exception as exc:
        logger.warning("[session_service] Session validation fallback for %s: %s", session_id, exc)
        return True


# Idle-timeout precision is traded for far fewer writes; keep this well
# below SESSION_IDLE_TIMEOUT_SECONDS.
TOUCH_INTERVAL_SECONDS = 60
_recent_touches: dict[str, tuple[float, tuple]] = {}


def touch_session(
    session_id: str | None, request: Request | None, *, keep_user_agent: bool = False
) -> None:
    """Record activity. ``keep_user_agent`` keeps a CLI session's label in place.

    Throttled per process: the row is rewritten at most once per
    ``TOUCH_INTERVAL_SECONDS`` unless the IP or user agent changed, so busy
    pages don't rewrite (and lock) the same session row on every request.
    """
    if not session_id:
        return
    request_ip, user_agent = _request_meta(request)
    if keep_user_agent:
        user_agent = None
    now = time.monotonic()
    fingerprint = (request_ip, user_agent)
    recent = _recent_touches.get(session_id)
    if recent and recent[1] == fingerprint and now - recent[0] < TOUCH_INTERVAL_SECONDS:
        return
    if len(_recent_touches) > 10_000:
        _recent_touches.clear()
    _recent_touches[session_id] = (now, fingerprint)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Detect IP/UA changes mid-session for anomaly auditing.
                cur.execute(
                    "SELECT request_ip, user_agent FROM user_sessions WHERE session_id = %s",
                    (session_id,),
                )
                prior = cur.fetchone() or {}
                cur.execute(
                    """
                    UPDATE user_sessions
                    SET last_seen_at = NOW(),
                        request_ip = COALESCE(%s, request_ip),
                        user_agent = COALESCE(%s, user_agent)
                    WHERE session_id = %s
                    """,
                    (request_ip, user_agent, session_id),
                )
            conn.commit()
        # Anomaly emit happens outside the DB transaction so it's never blocking.
        if prior:
            prior_ip = prior.get("request_ip")
            prior_ua = prior.get("user_agent")
            try:
                if request_ip and prior_ip and str(prior_ip) != str(request_ip):
                    from app.services.compliance.security_audit import record_security_event

                    record_security_event(
                        "session_ip_change",
                        session_id=session_id,
                        request_ip=request_ip,
                        action="session_use",
                        target_type="session",
                        target_id=str(session_id),
                        outcome="success",
                        user_agent=user_agent,
                        metadata={"previous_ip": str(prior_ip)},
                    )
                if user_agent and prior_ua and prior_ua != user_agent:
                    from app.services.compliance.security_audit import record_security_event

                    record_security_event(
                        "session_user_agent_change",
                        session_id=session_id,
                        request_ip=request_ip,
                        action="session_use",
                        target_type="session",
                        target_id=str(session_id),
                        outcome="success",
                        user_agent=user_agent,
                        metadata={"previous_user_agent": prior_ua[:200]},
                    )
            except Exception as exc:  # pragma: no cover - audit best-effort
                logger.debug("[session_service] anomaly emit failed: %s", exc)
    except Exception as exc:
        logger.debug("[session_service] Failed to touch session %s: %s", session_id, exc)


def revoke_session(session_id: str, user_id: str) -> bool:
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE user_sessions
                    SET revoked_at = NOW()
                    WHERE session_id = %s AND user_id = %s AND revoked_at IS NULL
                    """,
                    (session_id, user_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
        if updated:
            try:
                from app.security.step_up import revoke_step_up_for_session

                revoke_step_up_for_session(session_id)
            except Exception:
                pass
        return updated
    except Exception as exc:
        logger.warning("[session_service] Failed to revoke session %s: %s", session_id, exc)
        return False


def revoke_all_other_sessions(user_id: str, keep_session_id: str | None) -> int:
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if keep_session_id:
                    cur.execute(
                        """
                        UPDATE user_sessions
                        SET revoked_at = NOW()
                        WHERE user_id = %s
                          AND session_id <> %s
                          AND revoked_at IS NULL
                        """,
                        (user_id, keep_session_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE user_sessions
                        SET revoked_at = NOW()
                        WHERE user_id = %s
                          AND revoked_at IS NULL
                        """,
                        (user_id,),
                    )
                revoked = cur.rowcount
            conn.commit()
        return revoked
    except Exception as exc:
        logger.warning("[session_service] Failed to revoke other sessions for %s: %s", user_id, exc)
        return 0


def revoke_all_sessions(user_id: str) -> int:
    """Force-logout every active session for a user.

    Called on password reset, MFA reset, role change, or admin action so a
    compromised credential can be fully invalidated in one call.
    """
    return revoke_all_other_sessions(user_id, keep_session_id=None)


def list_user_sessions(user_id: str, current_session_id: str | None) -> list[dict[str, object]]:
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT session_id, created_at, expires_at, revoked_at, last_seen_at, request_ip, user_agent
                    FROM user_sessions
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT 20
                    """,
                    (user_id,),
                )
                rows = cur.fetchall() or []
        result: list[dict[str, object]] = []
        for row in rows:
            session_id = str(row.get("session_id") or "")
            result.append(
                {
                    "session_id": session_id,
                    "created_at": row.get("created_at"),
                    "expires_at": row.get("expires_at"),
                    "revoked_at": row.get("revoked_at"),
                    "last_seen_at": row.get("last_seen_at"),
                    "request_ip": row.get("request_ip"),
                    "user_agent": row.get("user_agent"),
                    "kind": session_kind(row.get("user_agent")),
                    "current": current_session_id == session_id,
                }
            )
        return result
    except Exception as exc:
        logger.warning("[session_service] Failed to list sessions for %s: %s", user_id, exc)
        return []
