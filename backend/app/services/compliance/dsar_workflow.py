"""DSAR operations workflow service.

Provides the **internal admin** queue + state machine that satisfies
the SOC 2 / GDPR / CCPA control requirement to *track* every
data-subject request from intake to closure with assignee, evidence,
and statutory deadline.

The user-facing self-service endpoints (``/api/dsar/access``,
``/portability``, ``/erase``, …) auto-open and auto-complete a
``dsar_requests`` row so that even instant flows have an auditor-
visible record. Slower flows (manual ID-verification, regulator
escalation, partial fulfilment) are managed by admins via the routes
in ``backend/app/routes/dsar_admin_routes.py``.

The state machine is intentionally small: open → in_progress →
{completed, escalated, rejected}. Every transition emits a
``security_audit_event`` so the audit chain (T14) is the source of
truth, not this row.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.database import get_database_url, get_db_connection
from app.db.rows import rows_to_dicts
from app.services.compliance.security_audit import record_security_event
from app.utils.logger import logger

VALID_TYPES = {
    "access",
    "portability",
    "rectification",
    "objection",
    "erasure",
    "restriction",
    "automated_decision_review",
}
VALID_STATUSES = {"open", "in_progress", "completed", "escalated", "rejected"}
TERMINAL_STATUSES = {"completed", "rejected"}

# Allowed state-machine edges. Terminal statuses (completed, rejected)
# are immutable: once a request closes, audit-trail integrity demands
# we never re-open it (a re-opened DSAR is, definitionally, a *new*
# request with its own statutory clock). ``escalated`` is a parking
# state — operations can move back to ``in_progress`` after they
# resolve the regulator/legal hold and then close.
ALLOWED_TRANSITIONS: dict[str, set] = {
    "open": {"in_progress", "completed", "escalated", "rejected"},
    "in_progress": {"completed", "escalated", "rejected"},
    "escalated": {"in_progress", "completed", "rejected"},
    "completed": set(),
    "rejected": set(),
}

# Statutory windows. CCPA-only requests get 45 days; GDPR + everything
# else defaults to 30 days. Per-request override allowed via sla_days.
DEFAULT_SLA_DAYS = 30
CCPA_SLA_DAYS = 45


def _sla_days_for(jurisdiction: str | None) -> int:
    if not jurisdiction:
        return DEFAULT_SLA_DAYS
    j = jurisdiction.upper()
    # Match both compact ("US-CA") and labelled ("US-PRIVACY:US-CA",
    # "CCPA:US-CA") jurisdiction strings produced by
    # privacy_jurisdiction.resolve_default_consent_for.
    if "US-CA" in j or j.endswith(":CA") or j.startswith("CCPA"):
        return CCPA_SLA_DAYS
    return DEFAULT_SLA_DAYS


def _now() -> datetime:
    return datetime.now(timezone.utc)


def open_request(
    *,
    request_type: str,
    subject_user_id: str | None = None,
    subject_email: str | None = None,
    jurisdiction: str | None = None,
    created_by: str | None = None,
    notes: str | None = None,
    sla_days: int | None = None,
    audit_event_id: str | None = None,
    auto_complete: bool = False,
) -> str | None:
    """Insert a new DSAR row and return its id (or ``None`` if no DB).

    ``auto_complete`` is used by the user-facing self-service endpoints
    that finish synchronously; the row is created and immediately
    transitioned to ``completed`` so admins still see a complete audit
    queue with zero manual data entry."""
    if request_type not in VALID_TYPES:
        raise ValueError(f"unknown DSAR request type: {request_type!r}")
    if not get_database_url():
        return None

    request_id = str(uuid.uuid4())
    received = _now()
    sla = int(sla_days or _sla_days_for(jurisdiction))
    due = received + timedelta(days=sla)
    completed = received if auto_complete else None
    status = "completed" if auto_complete else "open"

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dsar_requests
                        (id, type, subject_user_id, subject_email, jurisdiction,
                         status, received_at, due_at, completed_at, sla_days,
                         notes, evidence, audit_event_id, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        request_id,
                        request_type,
                        subject_user_id,
                        subject_email,
                        jurisdiction,
                        status,
                        received,
                        due,
                        completed,
                        sla,
                        notes,
                        json.dumps([]),
                        audit_event_id,
                        created_by,
                    ),
                )
            conn.commit()
    except Exception:
        logger.exception("[dsar_workflow] open_request failed")
        return None

    try:
        record_security_event(
            "dsar_request_opened",
            actor_id=created_by or subject_user_id or "anonymous",
            actor_type="user",
            action="dsar_request_opened",
            target_type="dsar_request",
            target_id=request_id,
            outcome="success",
            metadata={
                "type": request_type,
                "status": status,
                "sla_days": sla,
                "due_at": due.isoformat(),
                "jurisdiction": jurisdiction,
            },
        )
    except Exception:  # pragma: no cover
        logger.warning("[dsar_workflow] audit emit failed", exc_info=True)
    return request_id


def transition(  # noqa: C901
    *,
    request_id: str,
    new_status: str,
    actor_id: str,
    notes: str | None = None,
    evidence_entry: dict[str, Any] | None = None,
    assignee: str | None = None,
) -> bool:
    if new_status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {new_status!r}")
    if not get_database_url():
        return False

    completed_at_clause = ""
    completed = None
    if new_status in TERMINAL_STATUSES:
        completed = _now()
        completed_at_clause = ", completed_at = %s"

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Read current status under the same connection so the
                # state-machine check + UPDATE form an effective
                # critical section. Terminal statuses are immutable —
                # any attempt to leave ``completed``/``rejected`` is
                # rejected loudly so a stale admin tab cannot reopen a
                # closed request and silently restart its statutory
                # clock.
                cur.execute(
                    "SELECT status FROM dsar_requests WHERE id = %s FOR UPDATE",
                    (request_id,),
                )
                row = cur.fetchone()
                if not row:
                    return False
                current = row.get("status") if isinstance(row, dict) else row[0]
                allowed = ALLOWED_TRANSITIONS.get(current, set())
                if new_status not in allowed and new_status != current:
                    raise ValueError(f"transition {current!r} -> {new_status!r} not permitted")

                # Append evidence atomically.
                if evidence_entry is not None:
                    cur.execute(
                        """
                        UPDATE dsar_requests
                        SET evidence = COALESCE(evidence, '[]'::jsonb)
                                       || %s::jsonb
                        WHERE id = %s
                        """,
                        (json.dumps([evidence_entry]), request_id),
                    )
                params: list[Any] = [new_status]
                if assignee is not None:
                    params.append(assignee)
                if notes is not None:
                    params.append(notes)
                if completed is not None:
                    params.append(completed)
                params.append(request_id)
                cur.execute(
                    f"""
                    UPDATE dsar_requests
                    SET status = %s
                        {', assignee = %s' if assignee is not None else ''}
                        {', notes = %s' if notes is not None else ''}
                        {completed_at_clause}
                    WHERE id = %s
                    """,
                    tuple(params),
                )
                if cur.rowcount == 0:
                    return False
            conn.commit()
    except ValueError:
        raise
    except Exception:
        logger.exception("[dsar_workflow] transition failed (id=%s)", request_id)
        return False

    try:
        record_security_event(
            "dsar_request_transitioned",
            actor_id=actor_id,
            actor_type="admin",
            action="dsar_transition",
            target_type="dsar_request",
            target_id=request_id,
            outcome="success",
            metadata={
                "new_status": new_status,
                "assignee": assignee,
                "evidence_added": bool(evidence_entry),
            },
        )
    except Exception:  # pragma: no cover
        logger.warning("[dsar_workflow] audit emit failed", exc_info=True)
    return True


def list_requests(
    *,
    status: str | None = None,
    overdue_only: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if not get_database_url():
        return []
    where = ["1=1"]
    params: list[Any] = []
    if status:
        where.append("status = %s")
        params.append(status)
    if overdue_only:
        where.append("due_at < NOW() AND status NOT IN ('completed', 'rejected')")
    sql = f"""
        SELECT id, type, subject_user_id, subject_email, jurisdiction,
               status, assignee, received_at, due_at, completed_at,
               sla_days, audit_event_id, created_by
        FROM dsar_requests
        WHERE {' AND '.join(where)}
        ORDER BY due_at ASC
        LIMIT %s
    """
    params.append(int(limit))
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall() or []
    except Exception:
        logger.exception("[dsar_workflow] list_requests failed")
        return []
    keys = [
        "id",
        "type",
        "subject_user_id",
        "subject_email",
        "jurisdiction",
        "status",
        "assignee",
        "received_at",
        "due_at",
        "completed_at",
        "sla_days",
        "audit_event_id",
        "created_by",
    ]
    return rows_to_dicts(rows, keys)


def find_overdue(window_hours: int = 0) -> list[dict[str, Any]]:
    """Return open/in_progress requests whose deadline is within
    ``window_hours`` of now (or already past). Used by the deadline
    checker script to emit alerts."""
    if not get_database_url():
        return []
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT id, type, subject_user_id, status, due_at, sla_days
                    FROM dsar_requests
                    WHERE status NOT IN ('completed', 'rejected')
                      AND due_at < NOW() + (%s || ' hours')::interval
                    ORDER BY due_at ASC
                    """,
                (str(int(window_hours)),),
            )
            rows = cur.fetchall() or []
    except Exception:
        logger.exception("[dsar_workflow] find_overdue failed")
        return []
    keys = ["id", "type", "subject_user_id", "status", "due_at", "sla_days"]
    return rows_to_dicts(rows, keys)


__all__ = [
    "DEFAULT_SLA_DAYS",
    "CCPA_SLA_DAYS",
    "VALID_STATUSES",
    "VALID_TYPES",
    "find_overdue",
    "list_requests",
    "open_request",
    "transition",
]
