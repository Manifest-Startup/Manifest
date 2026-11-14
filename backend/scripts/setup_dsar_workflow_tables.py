"""DSAR operations workflow + breach timer schema (Task 15 follow-up).

Creates two tables that operationalise what was previously documentation
only:

- ``dsar_requests``      — internal admin queue with state machine,
                           assignee, statutory deadlines, evidence, and
                           audit linkage.
- ``incident_breach_timers`` — running per-incident clocks for the
                           GDPR 72h personal-data-breach window and the
                           HIPAA 60d notification window. Pairs with
                           docs/privacy/BREACH_NOTIFICATION.md and
                           docs/security/INCIDENT_RESPONSE_RUNBOOK.md.

Both tables are idempotent; safe to re-run on every boot.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import get_db_connection  # noqa: E402
from app.utils.logger import logger  # noqa: E402


DDL = [
    """
    CREATE TABLE IF NOT EXISTS dsar_requests (
        id              UUID PRIMARY KEY,
        type            TEXT NOT NULL,
        subject_user_id TEXT,
        subject_email   TEXT,
        jurisdiction    TEXT,
        status          TEXT NOT NULL DEFAULT 'open',
        assignee        TEXT,
        received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        due_at          TIMESTAMPTZ NOT NULL,
        completed_at    TIMESTAMPTZ,
        sla_days        INT NOT NULL,
        notes           TEXT,
        evidence        JSONB NOT NULL DEFAULT '[]'::jsonb,
        audit_event_id  UUID,
        created_by      TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_dsar_requests_status ON dsar_requests(status, due_at)",
    "CREATE INDEX IF NOT EXISTS idx_dsar_requests_subject ON dsar_requests(subject_user_id) WHERE subject_user_id IS NOT NULL",
    """
    CREATE TABLE IF NOT EXISTS incident_breach_timers (
        id                   UUID PRIMARY KEY,
        incident_id          TEXT NOT NULL,
        kind                 TEXT NOT NULL,
        opened_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        deadline_at          TIMESTAMPTZ NOT NULL,
        notified_at          TIMESTAMPTZ,
        regulator            TEXT,
        affected_count       INT,
        affected_jurisdiction TEXT,
        notes                TEXT,
        status               TEXT NOT NULL DEFAULT 'open',
        closed_at            TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_incident_breach_open ON incident_breach_timers(status, deadline_at)",
    "CREATE INDEX IF NOT EXISTS idx_incident_breach_incident ON incident_breach_timers(incident_id)",
]


def setup_dsar_workflow_tables() -> None:
    with get_db_connection() as conn:
        cur = conn.cursor()
        for stmt in DDL:
            try:
                cur.execute(stmt)
                logger.info(
                    "[dsar_workflow] applied: %s",
                    stmt.strip().split("\n")[0][:80],
                )
            except Exception as exc:
                logger.warning(
                    "[dsar_workflow] DDL skipped (%s): %s", stmt[:60], exc
                )
        conn.commit()
    logger.info("[dsar_workflow] migrations complete")


if __name__ == "__main__":
    setup_dsar_workflow_tables()
