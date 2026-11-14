"""Tests for the bug-fix attempt ingest layer."""

from __future__ import annotations

import json

import pytest

from app.db.database import InMemoryDatabaseClient
from app.services.operations import bug_fix as bfs


@pytest.fixture
def db():
    return InMemoryDatabaseClient()


def _payload(**overrides):
    base = {
        "github_issue_number": 42,
        "github_issue_url": "https://github.com/acme/manifest/issues/42",
        "issue_title": "[prod-test] landing — TypeError",
        "action": "diagnosis_posted",
        "confidence": "medium",
        "diagnosis_markdown": "Likely root cause...",
        "risks": ["might be a flaky network"],
        "suspected_files": ["frontend/src/App.tsx"],
        "model": "gpt-4o-mini",
        "input_tokens": 500,
        "output_tokens": 200,
        "model_cost_usd": 0.0002,
        "runner": "github-actions:bug-fix-agent",
    }
    base.update(overrides)
    return base


# ---------- validation ----------


def test_record_attempt_happy_path_persists_row(db):
    row = bfs.record_attempt(db=db, payload=_payload())
    assert row["id"]
    assert row["action"] == "diagnosis_posted"
    assert row["confidence"] == "medium"
    risks_value = row.get("risks")
    if isinstance(risks_value, str):
        risks_value = json.loads(risks_value)
    assert risks_value == ["might be a flaky network"]


def test_record_attempt_rejects_unknown_action(db):
    with pytest.raises(bfs.BugFixError):
        bfs.record_attempt(db=db, payload=_payload(action="explode_main"))


def test_record_attempt_rejects_unknown_confidence(db):
    with pytest.raises(bfs.BugFixError):
        bfs.record_attempt(db=db, payload=_payload(confidence="cosmic"))


def test_record_attempt_requires_issue_number(db):
    with pytest.raises(bfs.BugFixError):
        bfs.record_attempt(db=db, payload=_payload(github_issue_number=None))


def test_record_attempt_rejects_non_integer_issue_number(db):
    with pytest.raises(bfs.BugFixError):
        bfs.record_attempt(db=db, payload=_payload(github_issue_number="forty-two"))


def test_record_attempt_accepts_decline_with_no_confidence(db):
    row = bfs.record_attempt(
        db=db,
        payload=_payload(
            action="declined",
            confidence=None,
            diagnosis_markdown="not enough signal",
            risks=[],
            suspected_files=[],
        ),
    )
    assert row["action"] == "declined"
    assert row.get("confidence") is None


def test_record_attempt_accepts_failed_action(db):
    row = bfs.record_attempt(
        db=db,
        payload=_payload(
            action="failed",
            confidence=None,
            error_message="LLM timed out after 60s",
        ),
    )
    assert row["action"] == "failed"


def test_record_attempt_clamps_negative_token_counts(db):
    row = bfs.record_attempt(
        db=db,
        payload=_payload(input_tokens=-100, output_tokens=-50, model_cost_usd=-1.0),
    )
    assert row["input_tokens"] == 0
    assert row["output_tokens"] == 0
    assert float(row["model_cost_usd"]) == 0.0


# ---------- read APIs ----------


def test_list_recent_attempts_filters_by_issue(db):
    bfs.record_attempt(db=db, payload=_payload(github_issue_number=10))
    bfs.record_attempt(db=db, payload=_payload(github_issue_number=20))
    bfs.record_attempt(db=db, payload=_payload(github_issue_number=10))
    on_ten = bfs.list_recent_attempts(db=db, issue_number=10)
    assert len(on_ten) == 2


def test_list_recent_attempts_filters_by_action(db):
    bfs.record_attempt(db=db, payload=_payload(action="diagnosis_posted"))
    bfs.record_attempt(db=db, payload=_payload(action="declined", confidence=None))
    bfs.record_attempt(db=db, payload=_payload(action="failed", confidence=None))
    declined = bfs.list_recent_attempts(db=db, action="declined")
    assert len(declined) == 1
    assert declined[0]["action"] == "declined"


# ---------- stats ----------


def test_attempt_stats_rolls_up_correctly(db):
    bfs.record_attempt(db=db, payload=_payload(github_issue_number=1, action="diagnosis_posted", confidence="high"))
    bfs.record_attempt(db=db, payload=_payload(github_issue_number=1, action="diagnosis_posted", confidence="medium"))
    bfs.record_attempt(db=db, payload=_payload(github_issue_number=2, action="declined", confidence=None))
    bfs.record_attempt(db=db, payload=_payload(github_issue_number=3, action="failed", confidence=None,
                                                error_message="LLM crashed"))

    stats = bfs.get_attempt_stats(db=db, hours=168)
    assert stats["total_attempts"] == 4
    assert stats["by_action"]["diagnosis_posted"] == 2
    assert stats["by_action"]["declined"] == 1
    assert stats["by_action"]["failed"] == 1
    assert stats["by_confidence"]["high"] == 1
    assert stats["by_confidence"]["medium"] == 1
    assert stats["issues_touched"] == 3
    assert stats["top_retried_issues"][0]["github_issue_number"] == 1
    assert stats["top_retried_issues"][0]["attempts"] == 2
    assert stats["total_model_cost_usd"] > 0
