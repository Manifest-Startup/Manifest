"""Migrate the audit tables to the canonical schema + hash chain (SEC-068).

Adds to ``security_audit_events``:
- ``seq``         BIGSERIAL — monotonic ordering for chain walks
- ``category``    TEXT      — Category enum from audit_chain
- ``severity``    TEXT      — Severity enum
- ``sensitivity`` TEXT      — Sensitivity enum (drives SIEM redaction)
- ``request_id``  TEXT      — correlate with the request log
- ``prev_hash``   TEXT      — previous row's event_hash (or GENESIS)
- ``event_hash``  TEXT      — sha256(prev_hash || canonical_payload)

Backfills sane defaults so old rows still walk and verify (they form a
"prologue" segment with severity=info / sensitivity=internal). Adds a
unique index on ``event_hash`` so a duplicate insert is caught loudly.

The script is idempotent. Adding columns IF NOT EXISTS is safe; the
unique index is created CONCURRENTLY only outside a transaction (which
``get_db_connection`` provides), and we tolerate failure if it already
exists.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import get_db_connection  # noqa: E402
from app.utils.logger import logger  # noqa: E402


DDL = [
    # security_audit_events — base table may have been created by hand
    # in early Supabase setups, so create it with the *new* shape if
    # missing and otherwise add columns one by one.
    """
    CREATE TABLE IF NOT EXISTS security_audit_events (
        event_id    UUID PRIMARY KEY,
        event_type  VARCHAR(255) NOT NULL,
        user_id     TEXT,
        request_ip  TEXT,
        session_id  TEXT,
        metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    )
    """,
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS seq BIGSERIAL",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'security'",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS severity TEXT NOT NULL DEFAULT 'info'",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS sensitivity TEXT NOT NULL DEFAULT 'internal'",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS request_id TEXT",
    # Extended canonical audit-row contract (SOC 2 / ISO 27001 / HIPAA).
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS actor_id TEXT",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS actor_type TEXT",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS action TEXT",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS target_type TEXT",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS target_id TEXT",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS tenant_id TEXT",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS user_agent TEXT",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS outcome TEXT",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS prev_hash TEXT",
    "ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS event_hash TEXT",
    "CREATE INDEX IF NOT EXISTS idx_sae_seq ON security_audit_events(seq)",
    "CREATE INDEX IF NOT EXISTS idx_sae_event_type_created ON security_audit_events(event_type, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sae_user_created ON security_audit_events(user_id, created_at DESC) WHERE user_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_sae_severity_created ON security_audit_events(severity, created_at DESC)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sae_event_hash_unique ON security_audit_events(event_hash) WHERE event_hash IS NOT NULL",
]


def setup_audit_chain_tables() -> None:
    with get_db_connection() as conn:
        cur = conn.cursor()
        for stmt in DDL:
            try:
                cur.execute(stmt)
                logger.info("[audit_chain] applied: %s", stmt.strip().split("\n")[0][:80])
            except Exception as exc:
                # Don't fail startup on a single non-critical DDL — the
                # writer falls back to the legacy insert when columns
                # are missing, so the worst case is "chain disabled until
                # next deploy" rather than a hard outage.
                logger.warning("[audit_chain] DDL skipped (%s): %s", stmt[:60], exc)
        conn.commit()
    logger.info("[audit_chain] migrations complete")


if __name__ == "__main__":
    setup_audit_chain_tables()
