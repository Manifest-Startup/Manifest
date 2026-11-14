"""Tests for cost_tracking_service.

Covers pricing math, run lifecycle, monthly-spend aggregation, cap
read/write, the LLM usage tap, and the qualification-agent retrofit so
the wired cost-event path is exercised end-to-end against the in-memory
DB.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.db.database import InMemoryDatabaseClient
from app.services import cost_tracking_service as cts
from app.services import idea_qualification_service as qs
from app.services import llm_usage_tap


@pytest.fixture
def db():
    return InMemoryDatabaseClient()


# ---------- pricing math ----------


def test_compute_model_cost_known_model():
    cost = cts._compute_model_cost_usd(
        model="gpt-4o-mini",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    assert cost == pytest.approx(0.15, rel=1e-3)


def test_compute_model_cost_cached_input_discounted():
    full = cts._compute_model_cost_usd(model="gpt-4o-mini", input_tokens=1_000_000, output_tokens=0)
    cached = cts._compute_model_cost_usd(
        model="gpt-4o-mini",
        input_tokens=1_000_000,
        output_tokens=0,
        cached_input_tokens=1_000_000,
    )
    assert cached == pytest.approx(full * cts.CACHED_INPUT_DISCOUNT, rel=1e-6)


def test_compute_model_cost_unknown_falls_back_not_zero():
    cost = cts._compute_model_cost_usd(model="some-new-model", input_tokens=1_000_000, output_tokens=0)
    assert cost > 0, "unknown models must use the conservative fallback, never $0"


def test_compute_model_cost_clamps_negative_tokens_to_zero():
    cost = cts._compute_model_cost_usd(model="gpt-4o-mini", input_tokens=-50, output_tokens=-50)
    assert cost == 0.0


# ---------- run lifecycle ----------


def test_start_run_returns_id_and_persists(db):
    run_id = cts.start_agent_run(db=db, user_id="u1", agent_kind="qualification")
    assert run_id
    response = db.table("agent_runs").select("*").eq("id", run_id).limit(1).execute()
    row = response.data[0]
    assert row["status"] == "running"
    assert row["agent_kind"] == "qualification"
    assert row["total_billable_cost_usd"] == 0


def test_complete_run_marks_terminal(db):
    run_id = cts.start_agent_run(db=db, user_id="u1", agent_kind="qualification")
    cts.complete_agent_run(db=db, run_id=run_id, status="complete")
    row = db.table("agent_runs").select("*").eq("id", run_id).limit(1).execute().data[0]
    assert row["status"] == "complete"
    assert row["completed_at"]


def test_fail_run_records_error(db):
    run_id = cts.start_agent_run(db=db, user_id="u1", agent_kind="qualification")
    cts.fail_agent_run(db=db, run_id=run_id, error_message="LLM hard timeout")
    row = db.table("agent_runs").select("*").eq("id", run_id).limit(1).execute().data[0]
    assert row["status"] == "failed"
    assert row["error_message"] == "LLM hard timeout"


def test_complete_run_rejects_unknown_status(db):
    run_id = cts.start_agent_run(db=db, user_id="u1", agent_kind="qualification")
    with pytest.raises(ValueError):
        cts.complete_agent_run(db=db, run_id=run_id, status="bogus")


# ---------- cost event ingest ----------


def test_log_cost_event_inserts_and_bumps_run_totals(db):
    run_id = cts.start_agent_run(db=db, user_id="u1", agent_kind="qualification")
    event = cts.log_cost_event(
        db=db,
        user_id="u1",
        agent_kind="qualification",
        model="gpt-4o-mini",
        input_tokens=10_000,
        output_tokens=2_000,
        run_id=run_id,
    )
    # Cost computed and billable > model because of markup
    assert event["model_cost_usd"] > 0
    assert event["billable_cost_usd"] > event["model_cost_usd"]
    # Run totals reflect the event
    run = db.table("agent_runs").select("*").eq("id", run_id).limit(1).execute().data[0]
    assert run["total_input_tokens"] == 10_000
    assert run["total_output_tokens"] == 2_000
    assert run["total_billable_cost_usd"] == pytest.approx(event["billable_cost_usd"], rel=1e-6)


def test_log_cost_event_aggregates_multiple_calls(db):
    run_id = cts.start_agent_run(db=db, user_id="u1", agent_kind="qualification")
    cts.log_cost_event(db=db, user_id="u1", agent_kind="qualification", model="gpt-4o-mini",
                       input_tokens=1000, output_tokens=500, run_id=run_id)
    cts.log_cost_event(db=db, user_id="u1", agent_kind="qualification", model="gpt-4o-mini",
                       input_tokens=2000, output_tokens=1000, run_id=run_id)
    run = db.table("agent_runs").select("*").eq("id", run_id).limit(1).execute().data[0]
    assert run["total_input_tokens"] == 3000
    assert run["total_output_tokens"] == 1500


def test_log_cost_event_from_tap_uses_recorded_usage(db):
    llm_usage_tap.clear()
    llm_usage_tap.set_last_usage(
        "gpt-4o-mini",
        {"prompt_tokens": 500, "completion_tokens": 250},
    )
    run_id = cts.start_agent_run(db=db, user_id="u1", agent_kind="qualification")
    event = cts.log_cost_event_from_tap(
        db=db, user_id="u1", agent_kind="qualification", run_id=run_id
    )
    assert event is not None
    assert event["input_tokens"] == 500
    assert event["output_tokens"] == 250
    # And the tap is cleared after pop
    assert llm_usage_tap.peek_last_usage() is None


def test_log_cost_event_from_tap_returns_none_when_no_usage(db):
    llm_usage_tap.clear()
    run_id = cts.start_agent_run(db=db, user_id="u1", agent_kind="qualification")
    event = cts.log_cost_event_from_tap(
        db=db, user_id="u1", agent_kind="qualification", run_id=run_id
    )
    assert event is None


# ---------- user cost limits ----------


def test_get_user_cost_limits_creates_defaults_lazily(db):
    limits = cts.get_user_cost_limits(db=db, user_id="u1")
    assert limits["monthly_variable_cap_usd"] == float(cts.DEFAULT_MONTHLY_CAP_USD)
    assert limits["paused"] is False
    assert limits["base_subscription_usd"] == float(cts.DEFAULT_BASE_SUBSCRIPTION_USD)


def test_set_user_cost_limits_updates_cap_and_pause(db):
    cts.get_user_cost_limits(db=db, user_id="u1")  # seed defaults
    updated = cts.set_user_cost_limits(db=db, user_id="u1", monthly_variable_cap_usd=100.0)
    assert updated["monthly_variable_cap_usd"] == 100.0
    paused = cts.set_user_cost_limits(db=db, user_id="u1", paused=True)
    assert paused["paused"] is True


def test_set_user_cost_limits_clamps_negative_and_ceiling(db, monkeypatch):
    cts.get_user_cost_limits(db=db, user_id="u1")
    monkeypatch.setenv("MANIFEST_USER_CAP_MAX_USD", "500")
    above = cts.set_user_cost_limits(db=db, user_id="u1", monthly_variable_cap_usd=9999.0)
    assert above["monthly_variable_cap_usd"] == 500.0
    below = cts.set_user_cost_limits(db=db, user_id="u1", monthly_variable_cap_usd=-50.0)
    assert below["monthly_variable_cap_usd"] == 0.0


# ---------- dashboard query ----------


def test_dashboard_aggregates_by_kind_and_model(db):
    run_id = cts.start_agent_run(db=db, user_id="u1", agent_kind="qualification")
    cts.log_cost_event(db=db, user_id="u1", agent_kind="qualification", model="gpt-4o-mini",
                       input_tokens=1000, output_tokens=500, run_id=run_id)
    cts.log_cost_event(db=db, user_id="u1", agent_kind="qualification", model="gpt-4o",
                       input_tokens=1000, output_tokens=500, run_id=run_id)
    dashboard = cts.build_user_cost_dashboard(db=db, user_id="u1")
    assert dashboard["spend"]["event_count"] == 2
    assert "qualification" in dashboard["spend"]["by_agent_kind"]
    assert set(dashboard["spend"]["by_model"].keys()) == {"gpt-4o-mini", "gpt-4o"}
    assert dashboard["pct_of_cap"] >= 0
    assert dashboard["warn_level"] in {"ok", "elevated", "critical", "over"}


def test_dashboard_warn_level_thresholds(db):
    # Force a tiny cap so a single event tips into 'over'
    cts.set_user_cost_limits(db=db, user_id="u1", monthly_variable_cap_usd=0.0001)
    run_id = cts.start_agent_run(db=db, user_id="u1", agent_kind="qualification")
    cts.log_cost_event(db=db, user_id="u1", agent_kind="qualification", model="gpt-4o",
                       input_tokens=10_000, output_tokens=10_000, run_id=run_id)
    dashboard = cts.build_user_cost_dashboard(db=db, user_id="u1")
    assert dashboard["warn_level"] == "over"


def test_dashboard_isolation_across_users(db):
    run_a = cts.start_agent_run(db=db, user_id="userA", agent_kind="qualification")
    cts.log_cost_event(db=db, user_id="userA", agent_kind="qualification", model="gpt-4o",
                       input_tokens=1000, output_tokens=1000, run_id=run_a)
    run_b = cts.start_agent_run(db=db, user_id="userB", agent_kind="qualification")
    cts.log_cost_event(db=db, user_id="userB", agent_kind="qualification", model="gpt-4o",
                       input_tokens=99, output_tokens=99, run_id=run_b)
    dash_a = cts.build_user_cost_dashboard(db=db, user_id="userA")
    dash_b = cts.build_user_cost_dashboard(db=db, user_id="userB")
    assert dash_a["spend"]["total_input_tokens"] == 1000
    assert dash_b["spend"]["total_input_tokens"] == 99


# ---------- qualification retrofit ----------


def test_qualification_session_opens_an_agent_run(db):
    qs.start_session(db=db, user_id="u1", initial_idea_text="hi")
    runs = db.table("agent_runs").select("*").eq("user_id", "u1").execute().data
    assert len(runs) == 1
    assert runs[0]["agent_kind"] == "qualification"
    assert runs[0]["qualification_session_id"]


def test_qualification_turn_logs_cost_event_from_tap(db):
    session = qs.start_session(db=db, user_id="u1", initial_idea_text="hi")
    layer = MagicMock()
    layer.is_available.return_value = True
    # The qualification turn will call ai_layer.generate_structured_response;
    # we simulate the AIRouter writing into the tap as part of that call.
    def fake_call(*args, **kwargs):
        llm_usage_tap.set_last_usage(
            "gpt-4o-mini",
            {"prompt_tokens": 400, "completion_tokens": 100},
        )
        return {
            "extracted_fields": {},
            "decision": "ask_again",
            "next_question": "Q?",
        }
    layer.generate_structured_response.side_effect = fake_call

    qs.continue_session(
        db=db, ai_layer=layer, session_id=session["id"],
        user_id="u1", user_message="serious about this",
    )
    events = db.table("agent_cost_events").select("*").eq("user_id", "u1").execute().data
    assert len(events) == 1
    assert events[0]["input_tokens"] == 400
    assert events[0]["output_tokens"] == 100
    assert events[0]["agent_kind"] == "qualification"
    assert events[0]["model_cost_usd"] > 0


def test_qualification_completes_closes_agent_run(db):
    session = qs.start_session(db=db, user_id="u1", initial_idea_text="hi")
    layer = MagicMock()
    layer.is_available.return_value = True
    def fake_call(*args, **kwargs):
        llm_usage_tap.set_last_usage("gpt-4o-mini", {"prompt_tokens": 100, "completion_tokens": 50})
        return {
            "extracted_fields": {
                "user_seriousness": 9, "user_domain_knowledge": 8,
                "user_goals": "g", "user_budget": "b", "user_timeline": "t",
                "user_execution_ability": 7, "idea_market_need": 7,
                "idea_target_customer": "tc",
            },
            "decision": "complete",
            "qualification_score": 80,
            "qualification_explanation": "ok",
        }
    layer.generate_structured_response.side_effect = fake_call

    qs.continue_session(
        db=db, ai_layer=layer, session_id=session["id"],
        user_id="u1", user_message="enough info",
    )
    runs = db.table("agent_runs").select("*").eq("user_id", "u1").execute().data
    assert runs[0]["status"] == "complete"
    assert runs[0]["total_input_tokens"] == 100
    assert runs[0]["total_output_tokens"] == 50
