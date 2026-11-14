"""Focused tests for audit_retention.enforce_retention() semantics.

These tests mock the DB layer to assert the *control flow* invariants
that make the retention worker chain-safe:

1. The audit_retention_purge marker is emitted BEFORE any DELETE runs.
2. The DELETE predicate is bounded by both ``created_at < cutoff``
   AND ``seq < marker_seq`` so the marker (and anything newer) is
   never removed.
3. If the marker emit fails, no DELETE runs at all.
4. If the marker_seq cannot be resolved, no DELETE runs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.security import audit_retention


class _CursorRecorder:
    def __init__(self, marker_seq: int = 42, rowcount: int = 7):
        self.executed: list[tuple] = []
        self._marker_seq = marker_seq
        self.rowcount = rowcount

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return {"seq": self._marker_seq}


class _ConnRecorder:
    def __init__(self, cur):
        self._cur = cur
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self._cur

    def commit(self):
        self.committed = True


def test_marker_is_emitted_before_delete():
    """record_security_event must be called BEFORE any DB DELETE."""
    call_order: list[str] = []

    cur = _CursorRecorder()

    def _fake_record(*a, **kw):
        call_order.append("marker")

    def _fake_get_conn():
        call_order.append("db_open")
        return _ConnRecorder(cur)

    with patch.object(
        audit_retention, "get_db_connection", side_effect=_fake_get_conn
    ), patch(
        "app.services.compliance.security_audit.record_security_event",
        side_effect=_fake_record,
    ):
        result = audit_retention.enforce_retention()

    assert call_order[0] == "marker", call_order
    assert "db_open" in call_order
    assert result.deleted == cur.rowcount
    assert result.marker_seq == 42


def test_delete_predicate_bounds_by_marker_seq():
    """The DELETE must include ``seq < %s`` with marker_seq, so the
    marker row itself is provably untouchable."""
    cur = _CursorRecorder(marker_seq=99)

    def _fake_get_conn():
        return _ConnRecorder(cur)

    with patch.object(
        audit_retention, "get_db_connection", side_effect=_fake_get_conn
    ), patch(
        "app.services.compliance.security_audit.record_security_event",
        return_value=None,
    ):
        audit_retention.enforce_retention()

    # Find the DELETE statement and assert its shape + bound params.
    deletes = [(s, p) for (s, p) in cur.executed if "DELETE" in s.upper()]
    assert len(deletes) == 1, cur.executed
    sql, params = deletes[0]
    assert "seq < %s" in sql
    assert "created_at < %s" in sql
    assert params[1] == 99  # marker_seq is the second bind


def test_skipped_when_marker_emit_fails():
    """If we can't even emit the marker, we must NOT delete anything."""
    cur = _CursorRecorder()

    def _fake_get_conn():  # pragma: no cover - should never be called
        raise AssertionError("DB must not be touched when marker emit fails")

    with patch.object(
        audit_retention, "get_db_connection", side_effect=_fake_get_conn
    ), patch(
        "app.services.compliance.security_audit.record_security_event",
        side_effect=RuntimeError("sink down"),
    ):
        result = audit_retention.enforce_retention()

    assert result.skipped is True
    assert result.deleted == 0
    assert "sink down" in (result.reason or "")


def test_skipped_when_marker_seq_cannot_be_resolved():
    """If the marker lookup returns no row, we refuse to delete —
    deleting without a confirmed marker would erase history."""

    class _NoMarkerCursor(_CursorRecorder):
        def fetchone(self):
            return None

    cur = _NoMarkerCursor()

    def _fake_get_conn():
        return _ConnRecorder(cur)

    with patch.object(
        audit_retention, "get_db_connection", side_effect=_fake_get_conn
    ), patch(
        "app.services.compliance.security_audit.record_security_event",
        return_value=None,
    ):
        result = audit_retention.enforce_retention()

    # Only the SELECT ran; no DELETE.
    assert not any("DELETE" in s.upper() for (s, _) in cur.executed)
    assert result.skipped is True
    assert result.reason == "marker_seq_unknown"


def test_delete_predicate_includes_legacy_null_seq_rows():
    """Pre-chain rows (seq IS NULL) must still be purged after the
    retention floor — the predicate must be `(seq IS NULL OR seq <
    marker_seq)` so HIPAA/SOC2 retention isn't silently shortened or
    extended for legacy data."""
    cur = _CursorRecorder(marker_seq=10)
    with patch.object(audit_retention, "get_db_connection",
                       side_effect=lambda: _ConnRecorder(cur)), patch(
        "app.services.compliance.security_audit.record_security_event",
        return_value=None,
    ):
        audit_retention.enforce_retention()

    deletes = [(s, p) for (s, p) in cur.executed if "DELETE" in s.upper()]
    sql, _ = deletes[0]
    assert "seq IS NULL" in sql
    assert "seq < %s" in sql


def test_runner_script_imports_cleanly():
    """Regression: ensure scripts/run_audit_retention.py can be imported
    without ModuleNotFoundError regardless of CWD. The script must
    bootstrap sys.path the same way as other backend/scripts/* entry
    points so cron/systemd-timer can invoke it reliably."""
    import importlib.util
    import os

    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "scripts", "run_audit_retention.py",
    )
    assert os.path.exists(script_path), f"runner missing: {script_path}"
    spec = importlib.util.spec_from_file_location("_audit_runner_smoke", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # must not raise
    assert callable(mod.main)
