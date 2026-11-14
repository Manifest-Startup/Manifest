"""Tests for voice_testing_service.

Covers each of the three agents in isolation plus the end-to-end
orchestration:

  - User Simulation Agent: validation, happy path, defensive trims.
  - Stub executor: pulls user_input through to the LLM, returns text.
  - Evaluation Agent: normalization (score clamping, failure filter,
    pass requires all >= 3), empty-response auto-fail.
  - End-to-end: persists the row, links to three agent_runs, logs
    cost events, computes overall_score; continues past partial
    failure (executor blew up but simulator succeeded → row still
    written with assistant_response=NULL).
  - Read APIs: filters, stats roll-up.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.db.database import InMemoryDatabaseClient
from app.services import llm_usage_tap
from app.services import voice_testing_service as vts


@pytest.fixture
def db():
    return InMemoryDatabaseClient()


@pytest.fixture
def ai_layer():
    layer = MagicMock()
    layer.is_available.return_value = True
    return layer


def _stub_simulator_response(**overrides):
    base = {
        "user_persona": "Solo founder, mid-30s",
        "user_goal": "Get past a login error",
        "user_input": "Hey, um, my login keeps failing — I tried three times.",
        "expected_behavior": "Acknowledge the frustration, ask which step is failing.",
        "success_criteria": ["acknowledges frustration", "asks one clarifying question"],
        "failure_conditions": ["robotic tone", "ignores frustration"],
    }
    base.update(overrides)

    def _call(messages, *args, **kwargs):
        llm_usage_tap.set_last_usage("gpt-4o-mini", {"prompt_tokens": 200, "completion_tokens": 100})
        return base
    return _call


def _stub_evaluator_response(**overrides):
    base = {
        "scores": {
            "intent_understanding": 4,
            "emotional_awareness": 3,
            "helpfulness": 4,
        },
        "pass_status": True,
        "detected_failures": [],
        "root_cause_analysis": None,
        "recommended_fixes": [],
        "improved_response_example": "Quick check — did you reset your password recently?",
    }
    base.update(overrides)

    def _call(messages, *args, **kwargs):
        llm_usage_tap.set_last_usage("gpt-4o-mini", {"prompt_tokens": 400, "completion_tokens": 200})
        return base
    return _call


# ---------- User Simulation Agent ----------


def test_generate_test_case_rejects_unknown_scenario(ai_layer):
    with pytest.raises(vts.VoiceTestingError):
        vts.generate_test_case(ai_layer=ai_layer, scenario="bogus", emotion="neutral")


def test_generate_test_case_rejects_unknown_emotion(ai_layer):
    with pytest.raises(vts.VoiceTestingError):
        vts.generate_test_case(ai_layer=ai_layer, scenario="complaint", emotion="ecstatic")


def test_generate_test_case_requires_available_ai_layer():
    layer = MagicMock()
    layer.is_available.return_value = False
    with pytest.raises(vts.VoiceTestingError):
        vts.generate_test_case(ai_layer=layer, scenario="complaint", emotion="angry")


def test_generate_test_case_happy_path(ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_simulator_response()
    case = vts.generate_test_case(
        ai_layer=ai_layer, scenario="support_request", emotion="frustrated",
    )
    assert case["scenario"] == "support_request"
    assert case["emotion"] == "frustrated"
    assert case["user_input"]
    assert case["user_persona"]


def test_generate_test_case_rejects_empty_user_input(ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_simulator_response(user_input="   ")
    with pytest.raises(vts.VoiceTestingError):
        vts.generate_test_case(
            ai_layer=ai_layer, scenario="complaint", emotion="angry",
        )


# ---------- Evaluator normalization ----------


def test_evaluation_clamps_scores(ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_evaluator_response(
        scores={
            "intent_understanding": 9,
            "emotional_awareness": 0,
            "helpfulness": -2,
        },
    )
    result = vts.evaluate_response(
        ai_layer=ai_layer,
        test_case={
            "scenario": "complaint", "emotion": "angry",
            "user_input": "x", "expected_behavior": "y",
            "success_criteria": [], "failure_conditions": [],
        },
        assistant_response="Some response",
    )
    assert result["scores"]["intent_understanding"] == 5
    assert result["scores"]["emotional_awareness"] == 1
    assert result["scores"]["helpfulness"] == 1


def test_evaluation_pass_requires_all_scores_above_three(ai_layer):
    # Evaluator says pass=True but emotional_awareness is 2 → service
    # must override to pass=False.
    ai_layer.generate_structured_response.side_effect = _stub_evaluator_response(
        scores={
            "intent_understanding": 5,
            "emotional_awareness": 2,
            "helpfulness": 4,
        },
        pass_status=True,
    )
    result = vts.evaluate_response(
        ai_layer=ai_layer,
        test_case={
            "scenario": "complaint", "emotion": "angry",
            "user_input": "x", "expected_behavior": "y",
            "success_criteria": [], "failure_conditions": [],
        },
        assistant_response="Some response",
    )
    assert result["pass_status"] is False


def test_evaluation_filters_unknown_failure_taxonomy(ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_evaluator_response(
        detected_failures=["robotic_response", "wibble_wobble", "tone_mismatch"],
    )
    result = vts.evaluate_response(
        ai_layer=ai_layer,
        test_case={
            "scenario": "complaint", "emotion": "angry",
            "user_input": "x", "expected_behavior": "y",
            "success_criteria": [], "failure_conditions": [],
        },
        assistant_response="resp",
    )
    assert set(result["detected_failures"]) == {"robotic_response", "tone_mismatch"}


def test_evaluation_empty_response_short_circuits(ai_layer):
    # When the assistant_response is empty, the evaluator should NOT
    # be called — auto-fail to save tokens.
    ai_layer.generate_structured_response = MagicMock(side_effect=AssertionError("should not be called"))
    result = vts.evaluate_response(
        ai_layer=ai_layer,
        test_case={
            "scenario": "complaint", "emotion": "angry",
            "user_input": "x", "expected_behavior": "y",
            "success_criteria": [], "failure_conditions": [],
        },
        assistant_response="",
    )
    assert result["pass_status"] is False
    assert all(v == 1 for v in result["scores"].values())


# ---------- End-to-end orchestration ----------


def test_end_to_end_persists_row_and_links_three_runs(db, ai_layer):
    call_count = {"i": 0}

    def _route(messages, *args, **kwargs):
        call_count["i"] += 1
        # Call 1 = simulator, Call 2 = evaluator (executor uses generate_text).
        if call_count["i"] == 1:
            llm_usage_tap.set_last_usage("gpt-4o-mini", {"prompt_tokens": 200, "completion_tokens": 100})
            return {
                "user_persona": "p", "user_goal": "g",
                "user_input": "My payment failed",
                "expected_behavior": "ack + ask which step",
                "success_criteria": ["a"], "failure_conditions": ["b"],
            }
        llm_usage_tap.set_last_usage("gpt-4o-mini", {"prompt_tokens": 400, "completion_tokens": 200})
        return {
            "scores": {
                "intent_understanding": 4,
                "emotional_awareness": 3,
                "helpfulness": 4,
            },
            "pass_status": True,
            "detected_failures": [],
        }

    ai_layer.generate_structured_response.side_effect = _route
    # Executor uses generate_text rather than generate_structured_response.
    def _exec(messages, *args, **kwargs):
        llm_usage_tap.set_last_usage("gpt-4o-mini", {"prompt_tokens": 100, "completion_tokens": 50})
        return "Sorry that happened — was it card declined or a 3DS prompt?"
    ai_layer.generate_text.side_effect = _exec

    row = vts.run_test_case_end_to_end(
        db=db, ai_layer=ai_layer,
        triggered_by_user_id="admin-1",
        scenario="support_request", emotion="frustrated",
    )

    assert row["scenario"] == "support_request"
    assert row["user_emotion"] == "frustrated"
    assert row["assistant_response"]
    assert row["pass_status"] is True
    assert row["overall_score"] is not None

    # Three cost-tracked agent_runs were opened, all complete
    runs = db.table("agent_runs").select("*").eq("user_id", "admin-1").execute().data
    assert len(runs) == 3
    kinds = {r["agent_kind"] for r in runs}
    assert kinds == {"voice_test_simulator", "voice_test_executor", "voice_test_evaluator"}
    assert all(r["status"] == "complete" for r in runs)

    # Three cost events logged
    events = db.table("agent_cost_events").select("*").eq("user_id", "admin-1").execute().data
    assert len(events) == 3


def test_end_to_end_failed_simulator_raises(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = RuntimeError("LLM crashed")
    with pytest.raises(vts.VoiceTestingError):
        vts.run_test_case_end_to_end(
            db=db, ai_layer=ai_layer,
            triggered_by_user_id="admin-1",
            scenario="complaint", emotion="angry",
        )

    runs = db.table("agent_runs").select("*").eq("user_id", "admin-1").execute().data
    # Simulator run was opened then marked failed; no executor or evaluator runs.
    assert len(runs) == 1
    assert runs[0]["agent_kind"] == "voice_test_simulator"
    assert runs[0]["status"] == "failed"


def test_end_to_end_failed_executor_still_persists_row(db, ai_layer):
    """Executor blowing up should leave a row with assistant_response=null
    rather than dropping the test result entirely — operators want to see
    that the test was attempted."""
    ai_layer.generate_structured_response.side_effect = _stub_simulator_response()
    ai_layer.generate_text.side_effect = RuntimeError("executor unreachable")

    row = vts.run_test_case_end_to_end(
        db=db, ai_layer=ai_layer,
        triggered_by_user_id="admin-1",
        scenario="support_request", emotion="frustrated",
    )
    assert row["assistant_response"] is None
    assert row["pass_status"] is None  # not evaluated
    # Metadata captures the error for ops
    meta_raw = row.get("metadata")
    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    assert "executor" in (meta.get("error") or "").lower()


# ---------- read APIs ----------


def _seed_run(db, *, scenario, emotion, pass_status=True):
    """Insert a voice_test_run directly so list/stats tests don't need
    real LLM calls."""
    db.table(vts.TABLE).insert({
        "id": f"r-{scenario}-{emotion}-{pass_status}",
        "scenario": scenario,
        "user_persona": "p",
        "user_emotion": emotion,
        "user_input": "x",
        "expected_behavior": "y",
        "success_criteria": "[]",
        "failure_conditions": "[]",
        "executor_kind": "stub",
        "score_intent_understanding": 4 if pass_status else 2,
        "score_emotional_awareness": 3 if pass_status else 2,
        "score_helpfulness": 4 if pass_status else 2,
        "overall_score": 3.7 if pass_status else 2.0,
        "pass_status": pass_status,
        "detected_failures": json.dumps([] if pass_status else ["robotic_response"]),
        "recommended_fixes": "[]",
        "metadata": "{}",
        "triggered_by_user_id": "admin-1",
        # Relative timestamp: a fixed date here time-bombed test_stats_roll_up
        # once the stats window (hours=24*30) slid past it.
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }).execute()


def test_list_recent_runs_filters_by_scenario(db):
    _seed_run(db, scenario="support_request", emotion="frustrated")
    _seed_run(db, scenario="complaint", emotion="angry")
    _seed_run(db, scenario="product_question", emotion="confused")
    only_complaints = vts.list_recent_runs(db=db, scenario="complaint")
    assert len(only_complaints) == 1
    assert only_complaints[0]["scenario"] == "complaint"


def test_list_recent_runs_filters_by_emotion(db):
    _seed_run(db, scenario="support_request", emotion="frustrated")
    _seed_run(db, scenario="support_request", emotion="angry")
    frustrated = vts.list_recent_runs(db=db, emotion="frustrated")
    assert len(frustrated) == 1
    assert frustrated[0]["user_emotion"] == "frustrated"


def test_list_recent_runs_pass_only_filter(db):
    _seed_run(db, scenario="complaint", emotion="angry", pass_status=True)
    _seed_run(db, scenario="complaint", emotion="frustrated", pass_status=False)
    passed = vts.list_recent_runs(db=db, pass_only=True)
    failed = vts.list_recent_runs(db=db, pass_only=False)
    assert len(passed) == 1 and passed[0]["pass_status"] is True
    assert len(failed) == 1 and failed[0]["pass_status"] is False


def test_stats_roll_up(db):
    _seed_run(db, scenario="support_request", emotion="frustrated", pass_status=True)
    _seed_run(db, scenario="support_request", emotion="angry", pass_status=False)
    _seed_run(db, scenario="complaint", emotion="frustrated", pass_status=False)

    stats = vts.get_test_stats(db=db, hours=24 * 30)
    assert stats["total_runs"] == 3
    assert stats["passed"] == 1
    assert stats["failed"] == 2
    assert stats["pass_rate"] == pytest.approx(1 / 3, abs=1e-2)

    by_scen = {s["scenario"]: s for s in stats["by_scenario"]}
    assert by_scen["support_request"]["total"] == 2
    assert by_scen["complaint"]["total"] == 1

    failures = {f["failure"]: f["count"] for f in stats["top_failures"]}
    assert failures.get("robotic_response") == 2  # both failing rows seeded with this
