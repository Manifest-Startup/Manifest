"""Tests for the production-test results pipeline.

Covers persistence, validation, dedupe → existing issue linkage, fresh
issue creation, no-op on pass, environment-driven repo selection, and
the stats roll-up.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.database import InMemoryDatabaseClient
from app.services import production_test_service as pts


@pytest.fixture
def db():
    return InMemoryDatabaseClient()


def _payload(**overrides):
    base = dict(
        test_name="auth.login@chromium",
        status="pass",
        environment="production",
        severity="medium",
        runner="playwright",
        git_sha="deadbeef",
    )
    base.update(overrides)
    return pts.TestResultPayload(**base)


# ---------- persistence + validation ----------


def test_record_test_run_persists_row(db):
    row = pts.record_test_run(db=db, payload=_payload())
    assert row["id"]
    assert row["status"] == "pass"
    stored = (
        db.table("production_test_runs")
        .select("*")
        .eq("id", row["id"])
        .limit(1)
        .execute()
        .data
    )
    assert len(stored) == 1


def test_record_test_run_rejects_unknown_status(db):
    with pytest.raises(ValueError):
        pts.record_test_run(db=db, payload=_payload(status="weird"))


def test_record_test_run_rejects_unknown_severity(db):
    with pytest.raises(ValueError):
        pts.record_test_run(db=db, payload=_payload(severity="catastrophic"))


def test_record_test_run_requires_test_name(db):
    with pytest.raises(ValueError):
        pts.record_test_run(db=db, payload=_payload(test_name="   "))


# ---------- issue title / body shaping ----------


def test_issue_title_includes_first_error_line():
    title = pts._build_issue_title(
        "auth.login@chromium",
        "AssertionError: button not visible\nat line 42",
    )
    assert title.startswith("[prod-test] auth.login@chromium")
    assert "AssertionError" in title


def test_issue_title_truncates_long_error():
    long_msg = "X" * 500
    title = pts._build_issue_title("t", long_msg)
    assert len(title) < 250


def test_issue_body_contains_traceability():
    payload = _payload(
        status="fail",
        error_message="boom",
        stack_trace="frame1\nframe2",
        screenshot_url="https://artifacts/screenshot.png",
        suspected_files=["frontend/src/x.tsx"],
        ci_run_url="https://github.com/foo/bar/actions/runs/1",
        git_ref="refs/pull/42/head",
        console_errors=[{"text": "TypeError"}],
        network_errors=[{"url": "/api/x", "status": 500}],
    )
    body = pts._build_issue_body(payload, run_id="abc")
    assert "auth.login@chromium" in body
    assert "boom" in body
    assert "screenshot.png" in body
    assert "frontend/src/x.tsx" in body
    assert "https://github.com/foo/bar/actions/runs/1" in body
    assert "TypeError" in body
    assert "/api/x" in body


# ---------- dispatch behavior ----------


@pytest.mark.asyncio
async def test_pass_status_skips_issue_dispatch(db):
    row = pts.record_test_run(db=db, payload=_payload(status="pass"))
    result = await pts.maybe_create_issue_for_failure(
        db=db,
        payload=_payload(status="pass"),
        persisted_row=row,
    )
    assert result["action"] == "skip_non_failure"


@pytest.mark.asyncio
async def test_failure_without_repo_env_is_logged_but_not_filed(db, monkeypatch):
    monkeypatch.delenv("MANIFEST_GITHUB_REPO", raising=False)
    payload = _payload(status="fail", error_message="boom")
    row = pts.record_test_run(db=db, payload=payload)
    result = await pts.maybe_create_issue_for_failure(
        db=db, payload=payload, persisted_row=row
    )
    assert result["action"] == "skip_no_repo"


@pytest.mark.asyncio
async def test_failure_with_repo_creates_issue_via_github_service(db, monkeypatch):
    monkeypatch.setenv("MANIFEST_GITHUB_REPO", "acme/manifest")
    payload = _payload(status="fail", error_message="login button missing")
    row = pts.record_test_run(db=db, payload=payload)

    fake_svc = MagicMock()
    fake_svc.create_issues = AsyncMock(
        return_value={
            "created_issues": [
                {"number": 42, "url": "https://github.com/acme/manifest/issues/42"}
            ],
            "skipped_issues": [],
        }
    )
    fake_client = MagicMock()
    fake_client.aclose = AsyncMock()
    result = await pts.maybe_create_issue_for_failure(
        db=db,
        payload=payload,
        persisted_row=row,
        github_service=fake_svc,
        httpx_client=fake_client,
    )
    assert result["action"] == "created"
    assert result["issue"]["number"] == 42

    updated = (
        db.table("production_test_runs")
        .select("*")
        .eq("id", row["id"])
        .limit(1)
        .execute()
        .data[0]
    )
    assert updated["github_issue_number"] == 42
    assert "github.com/acme/manifest/issues/42" in updated["github_issue_url"]


@pytest.mark.asyncio
async def test_dedupe_records_existing_issue_url(db, monkeypatch):
    monkeypatch.setenv("MANIFEST_GITHUB_REPO", "acme/manifest")
    monkeypatch.setenv("MANIFEST_GITHUB_TOKEN", "tok")
    payload = _payload(status="fail", error_message="login button missing")
    row = pts.record_test_run(db=db, payload=payload)

    fake_svc = MagicMock()
    fake_svc.create_issues = AsyncMock(
        return_value={
            "created_issues": [],
            "skipped_issues": [{"title": "x", "reason": "existing_open_issue"}],
        }
    )

    fake_client = MagicMock()
    fake_client.aclose = AsyncMock()
    fake_get_response = MagicMock()
    fake_get_response.raise_for_status = MagicMock(return_value=None)
    fake_get_response.json = MagicMock(return_value=[
        {
            "title": pts._build_issue_title("auth.login@chromium", "login button missing"),
            "html_url": "https://github.com/acme/manifest/issues/7",
            "pull_request": None,
        }
    ])
    fake_client.get = AsyncMock(return_value=fake_get_response)

    result = await pts.maybe_create_issue_for_failure(
        db=db,
        payload=payload,
        persisted_row=row,
        github_service=fake_svc,
        httpx_client=fake_client,
    )
    assert result["action"] == "deduped"
    assert "issues/7" in (result.get("existing_url") or "")
    updated = (
        db.table("production_test_runs")
        .select("*")
        .eq("id", row["id"])
        .limit(1)
        .execute()
        .data[0]
    )
    assert "issues/7" in (updated.get("linked_existing_issue_url") or "")


@pytest.mark.asyncio
async def test_github_misconfig_returned_as_skip_not_raised(db, monkeypatch):
    monkeypatch.setenv("MANIFEST_GITHUB_REPO", "acme/manifest")
    monkeypatch.delenv("MANIFEST_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    payload = _payload(status="fail", error_message="boom")
    row = pts.record_test_run(db=db, payload=payload)

    fake_client = MagicMock()
    fake_client.aclose = AsyncMock()
    result = await pts.maybe_create_issue_for_failure(
        db=db, payload=payload, persisted_row=row, httpx_client=fake_client
    )
    assert result["action"] == "skip_no_token"


# ---------- read APIs ----------


def test_list_recent_runs_filters_by_status(db):
    for i in range(3):
        pts.record_test_run(db=db, payload=_payload(test_name=f"t{i}", status="pass"))
    pts.record_test_run(db=db, payload=_payload(test_name="boom", status="fail", error_message="x"))
    fails = pts.list_recent_runs(db=db, status="fail")
    assert len(fails) == 1
    assert fails[0]["test_name"] == "boom"


def test_failure_stats_rolls_up_correctly(db):
    pts.record_test_run(db=db, payload=_payload(status="pass"))
    pts.record_test_run(db=db, payload=_payload(status="pass"))
    pts.record_test_run(db=db, payload=_payload(test_name="flaky.t", status="flaky"))
    pts.record_test_run(db=db, payload=_payload(test_name="bad.a", status="fail", error_message="x"))
    pts.record_test_run(db=db, payload=_payload(test_name="bad.a", status="fail", error_message="y"))
    pts.record_test_run(db=db, payload=_payload(test_name="bad.b", status="error", error_message="z"))

    stats = pts.get_failure_stats(db=db, hours=24)
    assert stats["total_runs"] == 6
    assert stats["counts_by_status"]["pass"] == 2
    assert stats["counts_by_status"]["fail"] == 2
    assert stats["counts_by_status"]["error"] == 1
    assert stats["counts_by_status"]["flaky"] == 1
    assert 0 < stats["failure_rate"] < 1
    top = stats["top_failing_tests"]
    assert top[0]["test_name"] == "bad.a"
    assert top[0]["failures"] == 2
