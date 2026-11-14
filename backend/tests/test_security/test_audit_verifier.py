"""Tests for audit_verifier — runs over an in-memory row list to avoid DB."""

from __future__ import annotations

from datetime import datetime, timezone

from app.security.audit_chain import GENESIS_HASH, link_event
from app.security.audit_verifier import _verify_rows


def _build_chain(n: int, *, event_type: str = "login_success", with_extended: bool = False):
    rows = []
    prev = GENESIS_HASH
    for i in range(n):
        created_at = datetime(2026, 4, 19, 14, i, 0, tzinfo=timezone.utc)
        kwargs = dict(
            event_id=f"id-{i}",
            event_type=event_type,
            user_id="u",
            request_ip="1.2.3.4",
            session_id=None,
            request_id=None,
            metadata={"i": i},
            created_at_iso=created_at.isoformat(),
        )
        if with_extended:
            kwargs.update(
                actor_id="u", actor_type="user",
                action="login", target_type="user", target_id="u",
                tenant_id="t1", user_agent="ua/1.0", outcome="success",
            )
        defn, canonical, h = link_event(prev, **kwargs)
        row = {
            "seq": i + 1,
            "event_id": kwargs["event_id"],
            "event_type": kwargs["event_type"],
            "category": defn.category.value,
            "severity": defn.severity.value,
            "sensitivity": defn.sensitivity.value,
            "user_id": kwargs["user_id"],
            "request_ip": kwargs["request_ip"],
            "session_id": kwargs["session_id"],
            "request_id": kwargs["request_id"],
            "metadata": kwargs["metadata"],
            "prev_hash": prev,
            "event_hash": h,
            "created_at": created_at,
        }
        if with_extended:
            row.update(
                actor_id="u", actor_type="user",
                action="login", target_type="user", target_id="u",
                tenant_id="t1", user_agent="ua/1.0", outcome="success",
            )
        rows.append(row)
        prev = h
    return rows


def test_intact_chain_verifies():
    rows = _build_chain(5)
    report = _verify_rows(rows)
    assert report.is_intact
    assert report.total_rows == 5
    assert report.verified_rows == 5
    assert report.breaks == []


def test_tampered_metadata_breaks_chain():
    rows = _build_chain(4)
    # Mutate row #1's metadata after the fact — the recomputed hash
    # will no longer match the stored event_hash.
    rows[1]["metadata"] = {"i": 999}
    report = _verify_rows(rows)
    assert not report.is_intact
    assert any(b.reason == "event_hash mismatch" for b in report.breaks)


def test_deleted_row_breaks_chain():
    rows = _build_chain(4)
    # Drop the middle row: row[2]'s prev_hash now points at row[1],
    # but after deletion the new "previous walked hash" is row[0]'s
    # event_hash, so the prev_hash mismatch trips.
    del rows[1]
    report = _verify_rows(rows)
    assert not report.is_intact
    assert any(b.reason == "prev_hash mismatch" for b in report.breaks)


def test_reordered_rows_break_chain():
    rows = _build_chain(4)
    rows[1], rows[2] = rows[2], rows[1]
    report = _verify_rows(rows)
    assert not report.is_intact
    assert report.breaks  # at least one break recorded


def test_empty_chain_is_trivially_intact():
    report = _verify_rows([])
    assert report.is_intact
    assert report.total_rows == 0


def test_legacy_null_hash_rows_are_skipped_not_broken():
    """Pre-migration rows have NULL prev_hash/event_hash. The verifier
    must treat them as out-of-chain prologue, not as breaks."""
    legacy = [
        {
            "seq": 1, "event_id": "legacy-1", "event_type": "login_success",
            "category": "authn", "severity": "info", "sensitivity": "internal",
            "user_id": "u", "request_ip": "1.2.3.4", "session_id": None,
            "request_id": None, "metadata": {}, "prev_hash": None,
            "event_hash": None, "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        },
    ]
    chained = _build_chain(3)
    report = _verify_rows(legacy + chained)
    assert report.is_intact, report.breaks
    assert report.total_rows == 4
    assert report.verified_rows == 4


def test_window_anchor_prevents_false_break():
    """Verifying a window starting mid-chain must accept the in-window
    head's stored prev_hash as long as it matches the anchor we pass."""
    rows = _build_chain(5)
    anchor = rows[1]["event_hash"]  # caller would read this from the row before the window
    window = rows[2:]  # rows 2,3,4 — first row's prev_hash == anchor
    report = _verify_rows(window, anchor_prev_hash=anchor)
    assert report.is_intact, report.breaks
    assert report.total_rows == 3
    assert report.verified_rows == 3


def test_window_with_wrong_anchor_reports_break():
    rows = _build_chain(5)
    window = rows[2:]
    report = _verify_rows(window, anchor_prev_hash="0" * 64)
    assert not report.is_intact
    assert report.breaks[0].reason == "prev_hash mismatch"


def test_chain_with_extended_canonical_fields_verifies():
    """Rows that populate the new actor/action/target/outcome fields
    must still verify — confirms verifier parity with the writer's
    canonical_payload after the SOC 2 schema extension."""
    rows = _build_chain(4, with_extended=True)
    report = _verify_rows(rows)
    assert report.is_intact, report.breaks
    assert report.total_rows == 4
    assert report.verified_rows == 4


def test_extended_field_tampering_breaks_chain():
    rows = _build_chain(4, with_extended=True)
    rows[2]["target_id"] = "victim-account"  # silent mutation
    report = _verify_rows(rows)
    assert not report.is_intact
    # Either prev_hash or event_hash mismatch is acceptable here
    # — the point is that the tamper is detected.
    assert any("hash mismatch" in b.reason for b in report.breaks)


def test_retention_marker_preserves_chain_integrity_for_kept_rows():
    """The retention worker emits an audit_retention_purge marker
    BEFORE deleting the prefix. After the run the live table starts
    mid-history. The verifier must still verify the surviving slice
    end-to-end (which is the entire point of the marker-first design)."""
    rows = _build_chain(6, with_extended=True)
    # Simulate a retention run that deleted rows 0 and 1; the surviving
    # slice is rows[2:]. The first survivor's stored_prev points at
    # rows[1]["event_hash"] (a deleted row). The verifier's
    # "first chained row" branch accepts that as the new chain root.
    survivors = rows[2:]
    report = _verify_rows(survivors)
    assert report.is_intact, report.breaks
    assert report.total_rows == 4
    assert report.verified_rows == 4


def test_post_purge_marker_tampering_is_detected():
    """Critical: removing the verifier's purge-boundary blind spot
    means a row deleted/tampered immediately after an
    audit_retention_purge marker MUST surface as a real break."""
    rows = _build_chain(5, with_extended=True)
    # Inject a synthetic purge marker chained at index 2 by relabelling
    # rows[2] as the marker (its hash chain is still intact at this
    # point — this simulates the live table right after a retention
    # run that purged rows[0..1] and emitted the marker as rows[2]).
    rows[2]["event_type"] = "audit_retention_purge"
    # Now simulate an attacker silently deleting rows[3] from the
    # surviving slice. rows[4]'s stored prev_hash still points at
    # rows[3]'s hash, so the chain MUST break.
    survivors = [rows[2], rows[4]]
    report = _verify_rows(survivors)
    assert not report.is_intact
    assert any(b.reason == "prev_hash mismatch" for b in report.breaks), report.breaks


def test_post_purge_marker_tampering_of_next_row_is_detected():
    """Mutating the row immediately after a purge marker must also
    break verification — there is no boundary forgiveness."""
    rows = _build_chain(5, with_extended=True)
    rows[2]["event_type"] = "audit_retention_purge"
    rows[3]["target_id"] = "victim"  # silent post-marker mutation
    # Verifier walks rows[2:] (post-marker live slice).
    report = _verify_rows(rows[2:])
    assert not report.is_intact
    assert any("hash mismatch" in b.reason for b in report.breaks)


def test_chain_break_emits_detection_event_to_sink(monkeypatch):
    """Operational alerting contract: any verifier run that reports a
    break MUST emit a `detection_audit_chain_break` to the SIEM sink
    so on-call sees it within hours, not quarters."""
    from app.security import audit_verifier
    from app.security.audit_verifier import _alert_on_break, VerificationReport, ChainBreak

    captured = {}

    def _fake_emit(**kw):
        captured.update(kw)

    import app.security.audit_sink as sink_mod
    monkeypatch.setattr(sink_mod, "emit", _fake_emit)

    report = VerificationReport(
        total_rows=3, verified_rows=2,
        breaks=[ChainBreak(
            seq=2, event_id="ev-x", reason="event_hash mismatch",
            expected_hash="a" * 64, actual_hash="b" * 64,
        )],
    )
    _alert_on_break(report, scope="full")
    assert captured.get("event_type") == "detection_audit_chain_break"
    assert captured.get("severity") == "critical"
    assert captured["metadata"]["first_break"]["reason"] == "event_hash mismatch"


def test_chain_break_alert_skipped_when_intact(monkeypatch):
    from app.security.audit_verifier import _alert_on_break, VerificationReport

    called = {"n": 0}

    def _fake_emit(**kw):
        called["n"] += 1

    import app.security.audit_sink as sink_mod
    monkeypatch.setattr(sink_mod, "emit", _fake_emit)
    _alert_on_break(VerificationReport(total_rows=3, verified_rows=3), scope="full")
    assert called["n"] == 0
