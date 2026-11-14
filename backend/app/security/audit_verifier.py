"""Walk the security_audit_events hash chain and report breaks (SEC-068).

The hash chain in ``audit_chain.compute_event_hash`` is only useful if
something *checks* it. This module gives us two public entry points:

- ``verify_chain(limit=...)`` — read the chain in insertion order and
  recompute each ``event_hash`` from the stored payload + previous
  hash. Returns a structured report. Used by the nightly integrity
  job and by the operator-facing CLI.

- ``verify_chain_window(since=...)`` — same, but bounded to a time
  window so an on-call engineer can verify "the last 24 h" without
  scanning the full table.

A broken or missing link does not raise — we collect every break in
the report so an operator gets the full picture, then the caller
decides whether to alert / page.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.db.database import get_db_connection
from app.security.audit_chain import (
    GENESIS_HASH,
    canonical_payload,
    compute_event_hash,
)
from app.utils.logger import logger


@dataclass
class ChainBreak:
    seq: int
    event_id: str
    expected_hash: str
    actual_hash: str
    reason: str


@dataclass
class VerificationReport:
    total_rows: int = 0
    verified_rows: int = 0
    breaks: list[ChainBreak] = field(default_factory=list)

    @property
    def is_intact(self) -> bool:
        return not self.breaks and self.total_rows == self.verified_rows


def _row_canonical(row: dict) -> str:
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    created_at = row.get("created_at")
    if isinstance(created_at, datetime):
        created_iso = created_at.astimezone(timezone.utc).isoformat()
    else:
        created_iso = str(created_at or "")
    return canonical_payload(
        event_id=str(row.get("event_id") or ""),
        event_type=str(row.get("event_type") or ""),
        category=str(row.get("category") or ""),
        severity=str(row.get("severity") or ""),
        sensitivity=str(row.get("sensitivity") or ""),
        user_id=row.get("user_id"),
        request_ip=row.get("request_ip"),
        session_id=row.get("session_id"),
        request_id=row.get("request_id"),
        metadata=metadata,
        created_at_iso=created_iso,
        # Extended canonical fields (SOC 2 CC7.2 / ISO 27001 A.8.15).
        # Must be passed in the same order/shape as the writer or the
        # verifier will report a false event_hash mismatch on rows
        # that populate any of these.
        actor_id=row.get("actor_id"),
        actor_type=row.get("actor_type"),
        action=row.get("action"),
        target_type=row.get("target_type"),
        target_id=row.get("target_id"),
        tenant_id=row.get("tenant_id"),
        user_agent=row.get("user_agent"),
        outcome=row.get("outcome"),
    )


def _verify_rows(rows: list[dict], *, anchor_prev_hash: str | None = None) -> VerificationReport:
    """Verify a contiguous slice of the chain.

    Legacy rows that pre-date the chain migration carry NULL ``event_hash``
    / NULL ``prev_hash``. Those rows are skipped from chain verification
    (they are not part of any chain) but they still count toward
    ``total_rows`` so the operator can see how much of the table is
    "prologue" vs "chained".

    ``anchor_prev_hash`` lets the caller seed the expected predecessor
    hash — used by ``verify_chain_window`` so the first row in the
    window compares against the previous-row hash instead of GENESIS.
    """
    report = VerificationReport(total_rows=len(rows))
    prev_hash: str | None = anchor_prev_hash  # None until we hit the first chained row
    # Note: we deliberately do NOT special-case `audit_retention_purge`
    # markers here. The retention worker emits the marker BEFORE
    # deleting any rows (see ``audit_retention.enforce_retention``),
    # so the marker is correctly chained to the row that was tail at
    # the moment of the run. After deletion, the live table starts
    # mid-history and the existing "first chained row" branch below
    # accepts the survivor's stored prev_hash as the new chain root.
    # Any tamper or out-of-band deletion AFTER the marker is therefore
    # still surfaced as a real break — there is no boundary blind
    # spot.
    for row in rows:
        actual_raw = (row.get("event_hash") or "").strip().lower()
        stored_prev_raw = (row.get("prev_hash") or "").strip().lower()

        # Legacy / pre-chain rows: not part of any chain, do not verify.
        if not actual_raw:
            report.verified_rows += 1  # counted as "ok" — nothing to verify
            continue

        # First chained row we've seen — accept its stored prev_hash as
        # the chain root unless the caller anchored us explicitly.
        if prev_hash is None:
            prev_hash = stored_prev_raw or GENESIS_HASH

        canonical = _row_canonical(row)
        expected = compute_event_hash(prev_hash, canonical)
        stored_prev = stored_prev_raw or GENESIS_HASH

        if stored_prev != prev_hash:
            report.breaks.append(
                ChainBreak(
                    seq=int(row.get("seq") or 0),
                    event_id=str(row.get("event_id") or ""),
                    expected_hash=prev_hash,
                    actual_hash=stored_prev,
                    reason="prev_hash mismatch",
                )
            )
        elif actual_raw != expected:
            report.breaks.append(
                ChainBreak(
                    seq=int(row.get("seq") or 0),
                    event_id=str(row.get("event_id") or ""),
                    expected_hash=expected,
                    actual_hash=actual_raw,
                    reason="event_hash mismatch",
                )
            )
        else:
            report.verified_rows += 1
        # Advance using the stored hash so a subsequent intact row can
        # still verify even when the current row is a confirmed break.
        prev_hash = actual_raw
    return report


def verify_chain(limit: int | None = None) -> VerificationReport:
    """Verify the entire chain, optionally limited to the first ``limit`` rows."""
    sql = """
        SELECT seq, event_id, event_type, category, severity, sensitivity,
               user_id, request_ip, session_id, request_id, metadata,
               actor_id, actor_type, action, target_type, target_id,
               tenant_id, user_agent, outcome,
               event_hash, prev_hash, created_at
        FROM security_audit_events
        ORDER BY seq ASC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            rows = list(cur.fetchall() or [])
    except Exception as exc:
        logger.error("[audit_verifier] chain read failed: %s", exc)
        return VerificationReport()
    report = _verify_rows(rows)
    _alert_on_break(report, scope="full")
    return report


def verify_chain_window(*, since: datetime) -> VerificationReport:
    """Verify the chain over a recent window.

    Reads the immediately-preceding chained row (if any) so we can seed
    the expected ``prev_hash`` correctly; otherwise the first in-window
    row would be incorrectly compared against GENESIS and report a
    false break. The anchor row is *not* counted in the report.
    """
    since_utc = since.astimezone(timezone.utc)
    anchor_hash: str | None = None
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            # Anchor: the most recent chained row strictly before the window.
            cur.execute(
                """
                    SELECT event_hash
                    FROM security_audit_events
                    WHERE created_at < %s AND event_hash IS NOT NULL
                    ORDER BY seq DESC
                    LIMIT 1
                    """,
                (since_utc,),
            )
            anchor_row = cur.fetchone()
            if anchor_row:
                anchor_hash = (anchor_row.get("event_hash") or "").strip().lower() or None

            cur.execute(
                """
                    SELECT seq, event_id, event_type, category, severity, sensitivity,
                           user_id, request_ip, session_id, request_id, metadata,
                           actor_id, actor_type, action, target_type, target_id,
                           tenant_id, user_agent, outcome,
                           event_hash, prev_hash, created_at
                    FROM security_audit_events
                    WHERE created_at >= %s
                    ORDER BY seq ASC
                    """,
                (since_utc,),
            )
            rows = list(cur.fetchall() or [])
    except Exception as exc:
        logger.error("[audit_verifier] window read failed: %s", exc)
        return VerificationReport()
    report = _verify_rows(rows, anchor_prev_hash=anchor_hash)
    _alert_on_break(report, scope="window")
    return report


def _alert_on_break(report: VerificationReport, *, scope: str) -> None:
    """Emit a `detection_audit_chain_break` event to the SIEM sink the
    moment a verifier run reports an integrity break. This is the
    other half of the fail-closed contract: if the writer ever skips
    a chained insert, OR if a row is mutated/deleted out-of-band,
    THIS path makes sure on-call sees it within the next nightly
    verifier sweep instead of a quarterly audit.
    """
    if report.is_intact:
        return
    try:
        import uuid as _uuid

        from app.security import audit_sink

        audit_sink.emit(
            event_id=str(_uuid.uuid4()),
            event_type="detection_audit_chain_break",
            category="detection",
            severity="critical",
            sensitivity="restricted",
            user_id=None,
            request_ip=None,
            session_id=None,
            request_id=None,
            metadata={
                "scope": scope,
                "total_rows": report.total_rows,
                "verified_rows": report.verified_rows,
                "break_count": len(report.breaks),
                "first_break": (
                    {
                        "seq": report.breaks[0].seq,
                        "event_id": report.breaks[0].event_id,
                        "reason": report.breaks[0].reason,
                    }
                    if report.breaks
                    else None
                ),
            },
            event_hash="",
            prev_hash="",
            created_at_iso=datetime.now(timezone.utc).isoformat(),
        )
        logger.error(
            "[audit_verifier] CHAIN BREAK detected scope=%s breaks=%d first=%s",
            scope,
            len(report.breaks),
            report.breaks[0].reason if report.breaks else "?",
        )
    except Exception as exc:  # pragma: no cover - sink is best-effort
        logger.warning("[audit_verifier] failed to emit chain-break alert: %s", exc)


def quick_self_check() -> VerificationReport:
    """Cheap nightly job entry point — verifies the most recent 24 h."""
    return verify_chain_window(since=datetime.now(timezone.utc) - timedelta(days=1))
