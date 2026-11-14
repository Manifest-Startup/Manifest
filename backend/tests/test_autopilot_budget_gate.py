"""Tests for the Manifest Autopilot self-improvement loop.

Exercises the *decision* layer of ``backend/scripts/run_autopilot_agent.py``
(budget gate, denylist, diff-size guard, issue ranking, Claude-result parsing)
plus the ``get_daily_spend`` ledger helper the gate enforces against — all
without a DB, a network, or a real Claude run.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

# The orchestrator lives under backend/scripts (not importable as app.*).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import run_autopilot_agent as ap  # noqa: E402
from app.db.database import InMemoryDatabaseClient  # noqa: E402
from app.services.ai import cost_tracking as cts  # noqa: E402


@pytest.fixture
def db():
    return InMemoryDatabaseClient()


def _issue(number, title="t", labels=None, body="", is_pr=False):
    return ap.Issue(
        number=number,
        title=title,
        url="",
        body=body,
        labels=list(labels or []),
        is_pull_request=is_pr,
    )


# ---------- budget gate ----------


def test_budget_allows_when_under_cap():
    d = ap.evaluate_budget(spent_today_usd=5.0, daily_cap_usd=30.0, per_run_cap_usd=3.0)
    assert d["allowed"] is True
    assert d["remaining_usd"] == pytest.approx(25.0)


def test_budget_blocks_at_cap():
    d = ap.evaluate_budget(spent_today_usd=30.0, daily_cap_usd=30.0, per_run_cap_usd=3.0)
    assert d["allowed"] is False
    assert d["reason"] == "daily_cap_reached"


def test_budget_blocks_over_cap():
    d = ap.evaluate_budget(spent_today_usd=31.5, daily_cap_usd=30.0, per_run_cap_usd=3.0)
    assert d["allowed"] is False
    assert d["reason"] == "daily_cap_reached"


def test_budget_blocks_when_headroom_too_small_for_a_run():
    # $29.80 spent, $0.20 left — not enough for even a quarter of a $3 run.
    d = ap.evaluate_budget(spent_today_usd=29.8, daily_cap_usd=30.0, per_run_cap_usd=3.0)
    assert d["allowed"] is False
    assert d["reason"] == "insufficient_headroom"


def test_budget_fails_closed_on_unknown_spend():
    # spent_today_usd() returns +inf when the ledger is unreachable.
    d = ap.evaluate_budget(spent_today_usd=float("inf"), daily_cap_usd=30.0, per_run_cap_usd=3.0)
    assert d["allowed"] is False


def test_budget_blocks_when_cap_is_zero():
    d = ap.evaluate_budget(spent_today_usd=0.0, daily_cap_usd=0.0, per_run_cap_usd=3.0)
    assert d["allowed"] is False
    assert d["reason"] == "daily_cap_zero"


# ---------- denylist (self-modification guard) ----------


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/main.yml",
        "backend/app/auth/jwt.py",
        "backend/app/security/permissions.py",
        "backend/app/config/settings.py",
        "backend/scripts/run_autopilot_agent.py",
        "backend/scripts/run_pr_merge_train.py",
        "backend/scripts/run_security_autofix.py",
        "CODEOWNERS",
        ".github/CODEOWNERS",
        "docs/autopilot/PLAYBOOK.md",
        ".claude/skills/manifest-pitch-reel-cost-guard/SKILL.md",
    ],
)
def test_denylisted_paths_are_blocked(path):
    assert ap.path_is_denylisted(path) is True


@pytest.mark.parametrize(
    "path",
    ["backend/app/services/ideas/service.py", "frontend/src/features/ideas/Foo.tsx", "docs/API.md"],
)
def test_normal_paths_are_allowed(path):
    assert ap.path_is_denylisted(path) is False


def test_denylisted_changes_returns_offending_subset():
    changed = ["backend/app/services/foo.py", "backend/app/auth/jwt.py", "docs/API.md"]
    assert ap.denylisted_changes(changed) == ["backend/app/auth/jwt.py"]


# ---------- diff-size guard ----------


def test_diff_ok_within_envelope():
    r = ap.evaluate_diff(
        changed_paths=["backend/app/services/foo.py"],
        insertions=20,
        deletions=5,
        max_files=12,
        max_lines=600,
    )
    assert r["ok"] is True


def test_diff_rejects_denylisted():
    r = ap.evaluate_diff(
        changed_paths=["CODEOWNERS"], insertions=1, deletions=0, max_files=12, max_lines=600
    )
    assert r["ok"] is False and r["reason"] == "denylisted_paths"


def test_diff_rejects_empty():
    r = ap.evaluate_diff(changed_paths=[], insertions=0, deletions=0, max_files=12, max_lines=600)
    assert r["ok"] is False and r["reason"] == "empty_diff"


def test_diff_rejects_too_many_files():
    paths = [f"backend/app/services/f{i}.py" for i in range(13)]
    r = ap.evaluate_diff(
        changed_paths=paths, insertions=10, deletions=0, max_files=12, max_lines=600
    )
    assert r["ok"] is False and r["reason"] == "too_many_files"


def test_diff_rejects_too_many_lines():
    r = ap.evaluate_diff(
        changed_paths=["backend/app/services/foo.py"],
        insertions=500,
        deletions=200,
        max_files=12,
        max_lines=600,
    )
    assert r["ok"] is False and r["reason"] == "diff_too_large"


# ---------- issue selection / ranking ----------


def test_select_prefers_highest_priority():
    issues = [
        _issue(1, labels=["feature"]),
        _issue(2, labels=["automated-test", "priority:critical"]),
        _issue(3, labels=["bug"]),
    ]
    chosen = ap.select_issue(issues, busy_issue_numbers=set())
    assert chosen.number == 2


def test_select_skips_busy_and_skip_label_and_prs():
    issues = [
        _issue(1, labels=["bug"]),  # busy
        _issue(2, labels=["bug", ap.SKIP_LABEL]),  # opted out
        _issue(3, labels=["bug"], is_pr=True),  # a PR, not an issue
        _issue(4, labels=["documentation"]),  # not eligible
        _issue(5, labels=["enhancement"]),  # eligible
    ]
    chosen = ap.select_issue(issues, busy_issue_numbers={1})
    assert chosen.number == 5


def test_select_returns_none_when_nothing_eligible():
    issues = [_issue(1, labels=["documentation"]), _issue(2, labels=["question"])]
    assert ap.select_issue(issues, busy_issue_numbers=set()) is None


def test_hard_label_escalates_model():
    assert ap.model_for_issue(_issue(1, labels=[ap.HARD_LABEL]), default_model="m") == ap.HARD_MODEL
    assert ap.model_for_issue(_issue(1, labels=["bug"]), default_model="m") == "m"


def test_slugify_is_branch_safe():
    assert ap.slugify("Fix the Login Bug!! (urgent)") == "fix-the-login-bug-urgent"
    assert ap.slugify("") == "change"


# ---------- Codex result parsing ----------


def test_parse_codex_result_extracts_text_and_usage():
    # codex exec --json emits a JSONL stream; we recover the last agent message
    # and the token usage from whatever usage-shaped event appears.
    out = "\n".join(
        [
            '{"type":"thread.started","thread_id":"t1"}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"Did the thing."}}',
            '{"type":"turn.completed","usage":{"input_tokens":1200,"output_tokens":340}}',
        ]
    )
    parsed = ap.parse_codex_result(out)
    assert parsed["result_text"] == "Did the thing."
    assert parsed["input_tokens"] == 1200
    assert parsed["output_tokens"] == 340


def test_parse_codex_result_tolerates_no_usage():
    out = '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}'
    parsed = ap.parse_codex_result(out)
    assert parsed["result_text"] == "done"
    assert parsed["input_tokens"] == 0  # caller fills an estimate so spend is never $0
    assert parsed["output_tokens"] == 0


def test_estimate_tokens_never_zero():
    assert ap.estimate_tokens("") == 1
    assert ap.estimate_tokens("a" * 400) == 100


def test_repair_prompt_includes_failures_and_guards():
    prompt = ap.build_repair_prompt(
        issue=_issue(7, title="X"),
        checks_log="E501 line too long\nFAILED tests/test_foo.py::test_bar",
        max_files=12,
        max_lines=600,
    )
    # It must show the engine the real failures and keep the same guard rails.
    assert "E501" in prompt and "test_bar" in prompt
    assert "AUTOPILOT_DECLINE" in prompt
    assert "protected paths" in prompt
    assert "Do NOT commit" in prompt


def test_declined_from_result_detected():
    text = "Looked into it.\nAUTOPILOT_DECLINE: needs a schema migration beyond the size cap."
    assert "schema migration" in ap.declined_from_result(text)
    assert ap.declined_from_result("normal summary") is None


# ---------- get_daily_spend ledger helper ----------


def test_daily_spend_aggregates_today_for_agent_kind(db):
    # $30 of model cost: gpt-4 is $30/1M input, so 1M input tokens == $30.00.
    cts.log_cost_event(
        db=db,
        user_id=ap.SYSTEM_USER_ID,
        agent_kind="autopilot",
        model="gpt-4",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    spend = cts.get_daily_spend(db=db, agent_kind="autopilot")
    assert spend["total_model_cost_usd"] == pytest.approx(30.0, rel=1e-6)
    assert spend["event_count"] == 1


def test_daily_spend_excludes_other_agent_kinds(db):
    cts.log_cost_event(
        db=db,
        user_id="u1",
        agent_kind="qualification",
        model="gpt-4",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    spend = cts.get_daily_spend(db=db, agent_kind="autopilot")
    assert spend["total_model_cost_usd"] == 0.0
    assert spend["event_count"] == 0


def test_daily_spend_excludes_prior_days(db):
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    db.table("agent_cost_events").insert(
        {
            "id": "evt-old",
            "user_id": ap.SYSTEM_USER_ID,
            "agent_kind": "autopilot",
            "model": "gpt-4",
            "input_tokens": 1_000_000,
            "output_tokens": 0,
            "model_cost_usd": 30.0,
            "billable_cost_usd": 45.0,
            "created_at": yesterday,
        }
    ).execute()
    spend = cts.get_daily_spend(db=db, agent_kind="autopilot")
    assert spend["event_count"] == 0


def test_daily_spend_feeds_budget_gate_to_block(db):
    """End-to-end: a day already at the cap closes the gate."""
    cts.log_cost_event(
        db=db,
        user_id=ap.SYSTEM_USER_ID,
        agent_kind="autopilot",
        model="gpt-4",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    spent = cts.get_daily_spend(db=db, agent_kind="autopilot")["total_model_cost_usd"]
    decision = ap.evaluate_budget(spent_today_usd=spent, daily_cap_usd=30.0, per_run_cap_usd=3.0)
    assert decision["allowed"] is False
    assert decision["reason"] == "daily_cap_reached"
