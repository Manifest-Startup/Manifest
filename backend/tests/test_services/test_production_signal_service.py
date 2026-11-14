"""Tests for production signal deduping."""

from __future__ import annotations

from collections import defaultdict
from unittest.mock import AsyncMock

import pytest

from app.db.database import InMemoryDatabaseClient
from app.services.production_signal_service import ProductionSignalService


def _db():
    return InMemoryDatabaseClient(store=defaultdict(list))


def test_production_signal_info_not_counted(monkeypatch):
    monkeypatch.setenv("PRODUCTION_SIGNAL_THRESHOLD", "1")
    svc = ProductionSignalService()
    db = _db()
    out = svc.ingest(db, event_name="page_view", route="/", severity="info")
    assert out["skipped_reason"] == "info_severity_not_counted"


def test_production_signal_eligible_after_threshold(monkeypatch):
    monkeypatch.setenv("PRODUCTION_SIGNAL_THRESHOLD", "2")
    monkeypatch.delenv("PRODUCTION_SIGNAL_WINDOW_SECONDS", raising=False)
    svc = ProductionSignalService()
    db = _db()
    first = svc.ingest(db, event_name="client_error_boundary", route="/app", severity="error")
    assert first["github_eligible"] is False
    second = svc.ingest(db, event_name="client_error_boundary", route="/app", severity="error")
    assert second["event_count"] == 2
    assert second["github_eligible"] is True


@pytest.mark.asyncio
async def test_production_signal_github_path_updates_state(monkeypatch):
    monkeypatch.setenv("PRODUCTION_SIGNAL_THRESHOLD", "1")
    monkeypatch.setenv("MANIFEST_GITHUB_REPO", "owner/repo")
    svc = ProductionSignalService()
    svc.github_issue_service.create_issues = AsyncMock(
        return_value={
            "created_issues": [{"title": "t", "number": 99, "url": "https://gh/99", "node_id": "I_1"}],
            "created_count": 1,
            "skipped_existing_count": 0,
            "skipped_issues": [],
        }
    )
    db = _db()
    out = await svc.ingest_and_maybe_open_github(
        db,
        event_name="voice_session_aborted",
        route="/voice",
        severity="critical",
        create_github_issue=True,
    )
    assert out["github_issue_created"] is True
    assert out["github_issue_number"] == 99
    row = (db.table("production_signal_state").select("*").execute().data or [])[0]
    assert row["github_issue_number"] == 99
    assert row["last_issue_window_start"] == out["window_start"]
