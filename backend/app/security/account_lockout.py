"""Account lockout & exponential backoff (SEC-009).

Tracks failed-login attempts in two buckets — per-email and per-IP — so
a brute-force attacker hitting one account from many IPs is locked, and
a single IP credential-stuffing many emails is also locked.

Backoff schedule (seconds): 0, 0, 0, 0, 0, 30, 60, 120, 300, 600, 1800, 3600
Index = failed_attempts (clamped). After 12 attempts the bucket stays
locked for 1 hour at a time until manually cleared or until 24 h elapses
without further failures.

Tables: ``account_lockouts(bucket_kind, bucket_key, failed_attempts,
locked_until, first_failure_at, last_failure_at)``.

Failure mode: any DB error logs and returns "no lockout" so a DB outage
never locks every user out.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.database import get_db_connection
from app.utils.logger import logger

# Per-email & per-IP fail counts are tracked separately. Either lock triggers.
EMAIL_MAX_BEFORE_LOCK = 5
IP_MAX_BEFORE_LOCK = 20

_BACKOFF_SECONDS = [0, 0, 0, 0, 0, 30, 60, 120, 300, 600, 1800, 3600]
_MAX_LOCK_SECONDS = 3600
_BUCKET_TTL_SECONDS = 24 * 60 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _backoff_for(attempts: int) -> int:
    if attempts <= 0:
        return 0
    if attempts >= len(_BACKOFF_SECONDS):
        return _MAX_LOCK_SECONDS
    return _BACKOFF_SECONDS[attempts]


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower() or "unknown"


def _normalize_ip(ip: str | None) -> str:
    return (ip or "unknown").strip() or "unknown"


def is_locked(email: str | None, ip: str | None) -> tuple[bool, int]:
    """Return ``(locked, retry_after_seconds)``.

    ``retry_after_seconds`` is 0 when not locked.
    """
    keys = (
        ("email", _normalize_email(email)),
        ("ip", _normalize_ip(ip)),
    )
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT bucket_kind, locked_until
                    FROM account_lockouts
                    WHERE (bucket_kind, bucket_key) IN (
                        ('email', %s), ('ip', %s)
                    ) AND locked_until IS NOT NULL AND locked_until > NOW()
                    """,
                (keys[0][1], keys[1][1]),
            )
            rows = cur.fetchall() or []
    except Exception as exc:
        logger.warning("[lockout] is_locked DB error: %s", exc)
        return (False, 0)

    if not rows:
        return (False, 0)
    try:
        candidates = [row["locked_until"] for row in rows if row and row.get("locked_until")]
    except Exception:
        candidates = []
    if not candidates:
        return (False, 0)
    longest = max(candidates)
    try:
        delta = (longest - _now()).total_seconds()
    except Exception:
        return (False, 0)
    return (True, max(int(delta), 1))


def record_failure(email: str | None, ip: str | None) -> tuple[bool, int]:
    """Increment failure counters; return ``(now_locked, retry_after)`` for the worst bucket."""
    return _record_event(email, ip, success=False)


def record_success(email: str | None, ip: str | None) -> None:
    """Reset both buckets for the email (IP bucket is left alone — it
    aggregates across many emails and a successful login on one account
    shouldn't free the attacker's IP from rate-limiting)."""
    _record_event(email, ip, success=True)


def _record_event(email: str | None, ip: str | None, *, success: bool) -> tuple[bool, int]:
    email_key = _normalize_email(email)
    ip_key = _normalize_ip(ip)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if success:
                    cur.execute(
                        "DELETE FROM account_lockouts WHERE bucket_kind='email' AND bucket_key=%s",
                        (email_key,),
                    )
                    conn.commit()
                    return (False, 0)

                worst_lock = 0
                for kind, key, threshold in (
                    ("email", email_key, EMAIL_MAX_BEFORE_LOCK),
                    ("ip", ip_key, IP_MAX_BEFORE_LOCK),
                ):
                    cur.execute(
                        """
                        INSERT INTO account_lockouts
                            (bucket_kind, bucket_key, failed_attempts, last_failure_at, first_failure_at)
                        VALUES (%s, %s, 1, NOW(), NOW())
                        ON CONFLICT (bucket_kind, bucket_key) DO UPDATE SET
                            failed_attempts = CASE
                                WHEN account_lockouts.last_failure_at < NOW() - (%s || ' seconds')::interval
                                THEN 1
                                ELSE account_lockouts.failed_attempts + 1
                            END,
                            last_failure_at = NOW(),
                            first_failure_at = CASE
                                WHEN account_lockouts.last_failure_at < NOW() - (%s || ' seconds')::interval
                                THEN NOW()
                                ELSE account_lockouts.first_failure_at
                            END
                        RETURNING failed_attempts
                        """,
                        (kind, key, str(_BUCKET_TTL_SECONDS), str(_BUCKET_TTL_SECONDS)),
                    )
                    row = cur.fetchone()
                    attempts = int(row["failed_attempts"]) if row else 1
                    if attempts >= threshold:
                        backoff = _backoff_for(attempts)
                        if backoff > 0:
                            cur.execute(
                                """
                                UPDATE account_lockouts
                                SET locked_until = NOW() + (%s || ' seconds')::interval
                                WHERE bucket_kind=%s AND bucket_key=%s
                                """,
                                (str(backoff), kind, key),
                            )
                            worst_lock = max(worst_lock, backoff)
                conn.commit()
                return (worst_lock > 0, worst_lock)
    except Exception as exc:
        logger.warning("[lockout] record_event DB error: %s", exc)
        return (False, 0)


def admin_clear_lockout(*, email: str | None = None, ip: str | None = None) -> int:
    """Operator escape hatch — clears lockouts for a key. Returns rows removed."""
    where: list = []
    params: list = []
    if email:
        where.append("(bucket_kind='email' AND bucket_key=%s)")
        params.append(_normalize_email(email))
    if ip:
        where.append("(bucket_kind='ip' AND bucket_key=%s)")
        params.append(_normalize_ip(ip))
    if not where:
        return 0
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM account_lockouts WHERE {' OR '.join(where)}", params)
                removed = cur.rowcount
            conn.commit()
        return int(removed or 0)
    except Exception as exc:
        logger.warning("[lockout] admin_clear DB error: %s", exc)
        return 0
