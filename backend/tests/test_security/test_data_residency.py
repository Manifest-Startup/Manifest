"""Tests for data residency enforcement (Task #12)."""

from __future__ import annotations

import pytest

from app.security import data_residency as dr


def test_current_region_defaults_to_us(monkeypatch):
    monkeypatch.delenv("MANIFEST_DATA_REGION", raising=False)
    assert dr.current_region() == "us"


def test_current_region_env_override(monkeypatch):
    monkeypatch.setenv("MANIFEST_DATA_REGION", "EU")
    assert dr.current_region() == "eu"


def test_normalize_region_rejects_unsupported():
    with pytest.raises(ValueError):
        dr.normalize_region("antarctica")


def test_normalize_region_falls_back_when_empty():
    assert dr.normalize_region(None) == "us"
    assert dr.normalize_region("") == "us"


def test_assert_region_match_allows_same(monkeypatch):
    monkeypatch.setenv("MANIFEST_DATA_REGION", "eu")
    dr.assert_region_match("eu")  # no raise


def test_assert_region_match_blocks_mismatch(monkeypatch):
    monkeypatch.setenv("MANIFEST_DATA_REGION", "us")
    with pytest.raises(dr.RegionMismatchError):
        dr.assert_region_match("eu", context="integration_save")


def test_filter_to_current_region_drops_foreign(monkeypatch):
    monkeypatch.setenv("MANIFEST_DATA_REGION", "us")
    rows = [
        {"id": 1, "data_region": "us"},
        {"id": 2, "data_region": "eu"},
        {"id": 3, "data_region": None},  # treated as default us
    ]
    result = dr.filter_to_current_region(rows)
    ids = [r["id"] for r in result]
    assert ids == [1, 3]


# ---------------------------------------------------------------------------
# End-to-end residency enforcement on real write paths (Task #12).
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True


def test_save_integration_blocks_cross_region_write(monkeypatch):
    """save_integration must refuse when the user's pinned region differs
    from the process region — verifies the gate is wired into the actual
    write path, not just the helper."""
    from app.routes import oauth_routes

    monkeypatch.setenv("MANIFEST_DATA_REGION", "us")

    cur = _FakeCursor([{"data_region": "eu"}])
    conn = _FakeConn(cur)

    import contextlib

    @contextlib.contextmanager
    def _fake_get_db_connection():
        yield conn

    monkeypatch.setattr(oauth_routes, "get_db_connection", _fake_get_db_connection)

    result = oauth_routes.save_integration(
        "00000000-0000-0000-0000-000000000001",
        "google",
        {"access_token": "x", "refresh_token": "y"},
    )
    assert result is False
    # We must have read the user's region but never reached the INSERT.
    sqls = [s for s, _ in cur.executed]
    assert any("SELECT data_region FROM users" in s for s in sqls)
    assert not any("INSERT INTO integrations" in s for s in sqls)


def test_save_integration_allows_matching_region(monkeypatch):
    """Sanity check: matching region path proceeds past the residency gate."""
    from app.routes import oauth_routes

    monkeypatch.setenv("MANIFEST_DATA_REGION", "eu")
    monkeypatch.delenv("ENCRYPT_INTEGRATIONS_TOKENS", raising=False)

    cur = _FakeCursor([{"data_region": "eu"}])
    conn = _FakeConn(cur)

    import contextlib

    @contextlib.contextmanager
    def _fake_get_db_connection():
        yield conn

    monkeypatch.setattr(oauth_routes, "get_db_connection", _fake_get_db_connection)

    result = oauth_routes.save_integration(
        "00000000-0000-0000-0000-000000000001",
        "google",
        {"access_token": "x", "refresh_token": "y"},
    )
    assert result is True
    sqls = [s for s, _ in cur.executed]
    assert any("INSERT INTO integrations" in s for s in sqls)
