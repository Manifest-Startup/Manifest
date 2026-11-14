"""Personal-data breach timer service (Task 15 / T5 wiring).

Operationalises the breach-notification commitments in
``docs/privacy/BREACH_NOTIFICATION.md`` and
``docs/security/INCIDENT_RESPONSE_RUNBOOK.md``: when an incident is
classified as a personal-data breach, security calls
:func:`open_breach_timer` which pins the deadline (72 hours for
GDPR-affected subjects, 60 days for HIPAA-affected subjects), persists
the row in ``incident_breach_timers``, and emits a hash-chained audit
event. :func:`record_notification` and :func:`close_timer` close the
loop. :func:`find_due` is called by the breach-clock checker to alert
on approaching/breached deadlines.

The runbook docs reference these functions by name so the integration
is exercise-able, not narrative.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.database import get_database_url, get_db_connection
from app.db.rows import rows_to_dicts
from app.services.security_audit_service import record_security_event
from app.utils.logger import logger

GDPR_HOURS = 72
HIPAA_DAYS = 60

VALID_KINDS = {"gdpr", "hipaa", "ccpa"}
VALID_STATUSES = {"open", "notified", "closed"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _deadline_for(kind: str, opened_at: datetime) -> datetime:
    if kind == "gdpr":
        return opened_at + timedelta(hours=GDPR_HOURS)
    if kind == "hipaa":
        return opened_at + timedelta(days=HIPAA_DAYS)
    # CCPA: "without unreasonable delay"; we use 30 days as a defensible
    # operational target (matches GDPR DSAR window).
    return opened_at + timedelta(days=30)


def open_breach_timer(
    *,
    incident_id: str,
    kind: str,
    actor_id: str,
    affected_count: int | None = None,
    affected_jurisdiction: str | None = None,
    regulator: str | None = None,
    notes: str | None = None,
) -> str | None:
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown breach kind: {kind!r}")
    if not get_database_url():
        return None

    timer_id = str(uuid.uuid4())
    opened = _now()
    deadline = _deadline_for(kind, opened)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO incident_breach_timers
                        (id, incident_id, kind, opened_at, deadline_at,
                         affected_count, affected_jurisdiction, regulator,
                         notes, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'open')
                    """,
                    (
                        timer_id,
                        incident_id,
                        kind,
                        opened,
                        deadline,
                        affected_count,
                        affected_jurisdiction,
                        regulator,
                        notes,
                    ),
                )
            conn.commit()
    except Exception:
        logger.exception("[breach_timer] open failed (incident=%s)", incident_id)
        return None

    try:
        record_security_event(
            "breach_timer_opened",
            actor_id=actor_id,
            actor_type="admin",
            action="breach_timer_opened",
            target_type="incident",
            target_id=incident_id,
            outcome="success",
            metadata={
                "timer_id": timer_id,
                "kind": kind,
                "deadline_at": deadline.isoformat(),
                "affected_count": affected_count,
                "affected_jurisdiction": affected_jurisdiction,
                "regulator": regulator,
            },
        )
    except Exception:  # pragma: no cover
        logger.warning("[breach_timer] audit emit failed", exc_info=True)
    return timer_id


def record_notification(*, timer_id: str, actor_id: str, notes: str | None = None) -> bool:
    if not get_database_url():
        return False
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE incident_breach_timers
                    SET notified_at = NOW(), status = 'notified',
                        notes = COALESCE(%s, notes)
                    WHERE id = %s AND status = 'open'
                    """,
                    (notes, timer_id),
                )
                if cur.rowcount == 0:
                    return False
            conn.commit()
    except Exception:
        logger.exception("[breach_timer] notify failed (id=%s)", timer_id)
        return False
    try:
        record_security_event(
            "breach_timer_notified",
            actor_id=actor_id,
            actor_type="admin",
            action="breach_notification_sent",
            target_type="breach_timer",
            target_id=timer_id,
            outcome="success",
            metadata={},
        )
    except Exception:  # pragma: no cover
        logger.warning("[breach_timer] audit emit failed", exc_info=True)
    return True


def close_timer(*, timer_id: str, actor_id: str) -> bool:
    if not get_database_url():
        return False
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE incident_breach_timers
                    SET status = 'closed', closed_at = NOW()
                    WHERE id = %s AND status <> 'closed'
                    """,
                    (timer_id,),
                )
                if cur.rowcount == 0:
                    return False
            conn.commit()
    except Exception:
        logger.exception("[breach_timer] close failed (id=%s)", timer_id)
        return False
    try:
        record_security_event(
            "breach_timer_closed",
            actor_id=actor_id,
            actor_type="admin",
            action="breach_timer_closed",
            target_type="breach_timer",
            target_id=timer_id,
            outcome="success",
            metadata={},
        )
    except Exception:  # pragma: no cover
        logger.warning("[breach_timer] audit emit failed", exc_info=True)
    return True


def find_due(*, within_hours: int = 24) -> list[dict[str, Any]]:
    """Open timers whose deadline is within ``within_hours`` of now (or
    already past)."""
    if not get_database_url():
        return []
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT id, incident_id, kind, opened_at, deadline_at,
                           affected_count, regulator, status
                    FROM incident_breach_timers
                    WHERE status = 'open'
                      AND deadline_at < NOW() + (%s || ' hours')::interval
                    ORDER BY deadline_at ASC
                    """,
                (str(int(within_hours)),),
            )
            rows = cur.fetchall() or []
    except Exception:
        logger.exception("[breach_timer] find_due failed")
        return []
    keys = [
        "id",
        "incident_id",
        "kind",
        "opened_at",
        "deadline_at",
        "affected_count",
        "regulator",
        "status",
    ]
    return rows_to_dicts(rows, keys)


__all__ = [
    "GDPR_HOURS",
    "HIPAA_DAYS",
    "close_timer",
    "find_due",
    "open_breach_timer",
    "record_notification",
]
