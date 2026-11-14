"""Audit-log retention enforcement (SEC-068).

SOC 2 / ISO 27001 expect security audit records to be retained at
least **1 year**. HIPAA's record-retention requirement for security
incident documentation is **6 years**. We default the *retention
floor* to 1 year. HIPAA-regulated tenants opt in to the longer
window via ``AUDIT_RETENTION_DAYS`` (e.g. 2190 = 6 years).

Chain-preservation strategy
---------------------------
The hash chain in :mod:`audit_chain` is meaningful only if every
row's ``event_hash`` re-computes from the predecessor. We therefore
follow a **delete-prefix** strategy that keeps the surviving chain
verifiable end-to-end without rewriting any historical row:

1. Emit a single ``audit_retention_purge`` marker **before** any
   delete. This marker is appended to the live chain like any other
   event, so its ``prev_hash`` matches the row that was the tail at
   that moment.
2. Delete rows where ``created_at < cutoff`` **and** ``seq < marker_seq``.
   This guarantees we never delete the marker itself or anything
   newer than it. The marker's metadata records the cutoff for
   audit transparency.

After the run, the chain starts mid-history. The verifier handles
this in ``_verify_rows`` via the ``prev_hash is None`` branch — the
first chained row it sees becomes the new chain root for the walk.
The off-host SIEM JSONL stream still carries the full pre-purge
history, so an investigator can always reconstruct the deleted
range.

The worker is idempotent and best-effort: any DB failure logs at
WARNING and re-tries on the next invocation. We never raise into
the request path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.db.database import get_db_connection
from app.utils.logger import logger

_DEFAULT_RETENTION_DAYS = 365  # SOC 2 / ISO 27001 floor.


def _retention_days() -> int:
    raw = os.getenv("AUDIT_RETENTION_DAYS")
    if not raw:
        return _DEFAULT_RETENTION_DAYS
    try:
        n = int(raw.strip())
    except (TypeError, ValueError):
        logger.warning("[audit_retention] invalid AUDIT_RETENTION_DAYS=%r — using default", raw)
        return _DEFAULT_RETENTION_DAYS
    return max(n, _DEFAULT_RETENTION_DAYS)


@dataclass
class RetentionResult:
    deleted: int = 0
    cutoff: datetime | None = None
    marker_seq: int | None = None
    skipped: bool = False
    reason: str | None = None


def enforce_retention() -> RetentionResult:
    days = _retention_days()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Step 1 — emit the marker FIRST so the chain still has an
    # uninterrupted predecessor link at the moment of the marker.
    marker_seq: int | None = None
    try:
        from app.services.security_audit_service import record_security_event

        record_security_event(
            "audit_retention_purge",
            actor_type="system",
            action="audit_purge",
            target_type="security_audit_events",
            outcome="success",
            metadata={
                "retention_days": days,
                "cutoff_iso": cutoff.isoformat(),
                "strategy": "delete_prefix_with_marker",
            },
        )
    except Exception as exc:
        logger.warning("[audit_retention] marker emit failed: %s", exc)
        return RetentionResult(skipped=True, reason=str(exc), cutoff=cutoff)

    # Look up the marker we just wrote so we can guarantee we never
    # delete it (or anything newer) below.
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute("""
                    SELECT seq FROM security_audit_events
                    WHERE event_type = 'audit_retention_purge'
                    ORDER BY seq DESC LIMIT 1
                    """)
            row = cur.fetchone()
            if row:
                marker_seq = int(row.get("seq") or 0) or None
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("[audit_retention] marker lookup failed: %s", exc)

    if not marker_seq:
        # Defensive: we never delete without a confirmed marker
        # because that would erase history without an audit trail.
        return RetentionResult(skipped=True, reason="marker_seq_unknown", cutoff=cutoff)

    # Step 2 — delete the prefix. The (seq < marker_seq OR seq IS NULL)
    # guard makes absolutely sure we never delete the marker itself
    # while still purging legacy pre-chain rows that were written
    # before the seq column existed (those rows have NULL seq and
    # can never be `>= marker_seq`, so including them is safe).
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM security_audit_events
                    WHERE created_at < %s
                      AND (seq IS NULL OR seq < %s)
                    """,
                    (cutoff, marker_seq),
                )
                deleted = cur.rowcount or 0
            conn.commit()
    except Exception as exc:
        logger.warning("[audit_retention] delete failed: %s", exc)
        return RetentionResult(skipped=True, reason=str(exc), cutoff=cutoff, marker_seq=marker_seq)

    return RetentionResult(deleted=deleted, cutoff=cutoff, marker_seq=marker_seq)


__all__ = ["enforce_retention", "RetentionResult"]
