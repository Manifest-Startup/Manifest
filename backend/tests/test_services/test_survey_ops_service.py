"""Tests for survey analytics and GitHub triage helpers."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.db.database import InMemoryDatabaseClient
from app.services.operations.survey_ops import SurveyOpsService


def _row(survey_type: str, answers, *, days_ago: int = 1, response_id: str | None = None):
    created_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "response_id": response_id or f"{survey_type}-{created_at}",
        "survey_type": survey_type,
        "answers": answers,
        "created_at": created_at,
    }


def _db_with_rows(rows):
    db = InMemoryDatabaseClient(store=defaultdict(list))
    for row in rows:
        db.table("survey_responses").insert(row).execute()
    return db


def test_get_summary_aggregates_marketability_and_product_pull_signals():
    service = SurveyOpsService()
    db = _db_with_rows(
        [
            _row(
                "research",
                {
                    "signup_intent": 5,
                    "wants_call": "yes",
                    "value_prop": "Investor- or share-ready outputs without starting from scratch",
                    "biggest_barrier": "Doing market research or finding comparable companies",
                    "first_output": "A market / comparable research brief",
                    "trust_signal": "Citations or links behind claims and research",
                    "friction": "I need sources and citations before I can trust the research.",
                },
                response_id="r1",
            ),
            _row(
                "research",
                {
                    "signup_intent": 3,
                    "wants_call": "no",
                    "value_prop": "Investor- or share-ready outputs without starting from scratch",
                    "biggest_barrier": "Doing market research or finding comparable companies",
                    "first_output": "A market / comparable research brief",
                    "trust_signal": "Citations or links behind claims and research",
                    "clarity": "The product needs clearer proof and source links.",
                },
                response_id="r2",
            ),
            _row(
                "product_feedback",
                {
                    "main_benefit": "It gives shape to rough ideas faster",
                    "primary_task": "Generate or refine documents (deck, PRD, canvas, patent, etc.)",
                    "progress_score": 4,
                    "deliverable_score": 4,
                    "ai_quality": 5,
                    "pmf_disappointment": "Very disappointed",
                    "nps": 9,
                    "top_fix": "More citations in research outputs.",
                },
                response_id="p1",
            ),
            _row(
                "product_feedback",
                {
                    "main_benefit": "It gives shape to rough ideas faster",
                    "primary_task": "Generate or refine documents (deck, PRD, canvas, patent, etc.)",
                    "progress_score": 3,
                    "deliverable_score": 4,
                    "ai_quality": 4,
                    "pmf_disappointment": "Somewhat disappointed",
                    "nps": 8,
                    "confusing": "The onboarding is a bit confusing in the first session.",
                },
                response_id="p2",
            ),
        ]
    )

    summary = service.get_summary(db, include_issue_candidates=True, min_theme_count=1)

    assert summary["total_responses"] == 4
    assert summary["research_responses"] == 2
    assert summary["product_feedback_responses"] == 2
    assert summary["research_signup_intent_avg"] == 4.0
    assert summary["research_follow_up_rate"] == 50.0
    assert summary["product_nps_score"] == 50
    assert summary["top_research_value_props"][0]["label"] == "Investor- or share-ready outputs without starting from scratch"
    assert summary["top_action_themes"][0]["theme"] == "Research credibility"
    assert any(candidate["title"] == "Add citations and source tracing to Manifest research outputs" for candidate in summary["issue_candidates"])


@pytest.mark.asyncio
async def test_sync_issues_uses_github_helper_when_issue_creation_is_enabled():
    service = SurveyOpsService()
    service.github_issue_service.create_issues = AsyncMock(
        return_value={
            "repo": "Manifest-Startup/Manifest",
            "create_requested": True,
            "dry_run": False,
            "created_count": 1,
            "skipped_existing_count": 0,
            "created_issues": [{"title": "Add citations and source tracing to Manifest research outputs", "number": 12, "url": "https://github.com/test/12"}],
            "skipped_issues": [],
        }
    )
    db = _db_with_rows(
        [
            _row(
                "research",
                {
                    "signup_intent": 5,
                    "wants_call": "yes",
                    "first_output": "A market / comparable research brief",
                    "trust_signal": "Citations or links behind claims and research",
                    "friction": "Need citations and source evidence.",
                },
            ),
            _row(
                "research",
                {
                    "signup_intent": 4,
                    "wants_call": "yes",
                    "first_output": "A market / comparable research brief",
                    "trust_signal": "Citations or links behind claims and research",
                    "clarity": "Sources are the missing trust signal.",
                },
            ),
        ]
    )

    result = await service.sync_issues(
        db,
        max_issues=3,
        min_theme_count=1,
        create_github_issues=True,
        dry_run=False,
        extra_labels=["triage"],
    )

    assert result["github"]["created_count"] == 1
    service.github_issue_service.create_issues.assert_awaited_once()
    call_kwargs = service.github_issue_service.create_issues.await_args.kwargs
    assert call_kwargs["extra_labels"] == ["triage"]
    assert call_kwargs["repo"] == "Manifest-Startup/Manifest"


def test_get_summary_handles_large_batches_quickly():
    service = SurveyOpsService()
    rows = []
    for index in range(2500):
        rows.append(
            _row(
                "research" if index % 2 == 0 else "product_feedback",
                {
                    "signup_intent": 4,
                    "wants_call": "yes",
                    "value_prop": "One workspace instead of a pile of tools",
                    "biggest_barrier": "Keeping momentum and following through consistently",
                    "first_output": "A one-page idea summary",
                    "trust_signal": "Outputs that already look polished enough to share",
                    "main_benefit": "It creates drafts instead of starting from a blank page",
                    "primary_task": "Generate or refine documents (deck, PRD, canvas, patent, etc.)",
                    "progress_score": 4,
                    "deliverable_score": 4,
                    "ai_quality": 4,
                    "pmf_disappointment": "Very disappointed",
                    "nps": 9,
                    "friction": "Need clearer onboarding for the first session.",
                },
                response_id=f"row-{index}",
            )
        )
    db = _db_with_rows(rows)

    started_at = time.perf_counter()
    summary = service.get_summary(db, include_issue_candidates=True, min_theme_count=3)
    duration = time.perf_counter() - started_at

    assert summary["total_responses"] == 2500
    assert duration < 1.5
