"""Tests for the admin cost-overview aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.database import InMemoryDatabaseClient
from app.services.ai import admin_costs as acs
from app.services.ai import cost_tracking as cts
from app.services.operations import production_tests as pts


@pytest.fixture
def db():
    return InMemoryDatabaseClient()


def _seed_run_with_events(
    db,
    *,
    user_id: str,
    agent_kind: str,
    events: list,
    status: str = "complete",
    started_offset_minutes: int = 0,
):
    """Helper: create a run + N cost events for it."""
    run_id = cts.start_agent_run(db=db, user_id=user_id, agent_kind=agent_kind)
    if started_offset_minutes:
        started = (datetime.now(timezone.utc) - timedelta(minutes=started_offset_minutes)).isoformat()
        db.table("agent_runs").update({"started_at": started}).eq("id", run_id).execute()
    for ev in events:
        cts.log_cost_event(
            db=db,
            user_id=user_id,
            agent_kind=agent_kind,
            model=ev.get("model", "gpt-4o-mini"),
            input_tokens=ev.get("input_tokens", 1000),
            output_tokens=ev.get("output_tokens", 500),
            run_id=run_id,
        )
    cts.complete_agent_run(db=db, run_id=run_id, status=status)
    return run_id


# ---------- empty repo ----------


def test_overview_on_empty_repo_returns_zeroed_shape(db):
    overview = acs.build_admin_cost_overview(db=db)
    assert overview["totals"]["total_billable_usd"] == 0
    assert overview["totals"]["active_users"] == 0
    assert overview["totals"]["total_runs"] == 0
    assert overview["daily_series"] == []
    assert overview["top_users"] == []
    assert overview["by_agent_kind"] == []
    assert overview["expensive_runs"] == []
    assert overview["window_days"] == acs.DEFAULT_WINDOW_DAYS


# ---------- roll-ups ----------


def test_overview_aggregates_by_user_agent_and_model(db):
    _seed_run_with_events(db, user_id="u1", agent_kind="qualification", events=[
        {"model": "gpt-4o-mini", "input_tokens": 1000, "output_tokens": 500},
        {"model": "gpt-4o-mini", "input_tokens": 2000, "output_tokens": 1000},
    ])
    _seed_run_with_events(db, user_id="u2", agent_kind="bmc_value_propositions", events=[
        {"model": "gpt-4o", "input_tokens": 5000, "output_tokens": 2000},
    ])
    overview = acs.build_admin_cost_overview(db=db)
    kinds = {row["label"]: row["billable_usd"] for row in overview["by_agent_kind"]}
    models = {row["label"]: row["billable_usd"] for row in overview["by_model"]}
    users = {row["user_id"]: row["billable_usd"] for row in overview["top_users"]}

    assert set(kinds) == {"qualification", "bmc_value_propositions"}
    assert set(models) == {"gpt-4o-mini", "gpt-4o"}
    assert set(users) == {"u1", "u2"}
    assert users["u2"] > users["u1"]


def test_top_users_sorted_descending(db):
    _seed_run_with_events(db, user_id="tiny", agent_kind="qualification", events=[
        {"input_tokens": 100, "output_tokens": 50},
    ])
    _seed_run_with_events(db, user_id="big", agent_kind="qualification", events=[
        {"input_tokens": 100_000, "output_tokens": 50_000},
    ])
    overview = acs.build_admin_cost_overview(db=db)
    ranked = [u["user_id"] for u in overview["top_users"]]
    assert ranked[0] == "big"
    assert ranked[1] == "tiny"


def test_failed_run_counter(db):
    _seed_run_with_events(db, user_id="u1", agent_kind="qualification", events=[
        {"input_tokens": 100, "output_tokens": 50},
    ])
    _seed_run_with_events(db, user_id="u1", agent_kind="qualification", events=[
        {"input_tokens": 100, "output_tokens": 50},
    ], status="failed")
    overview = acs.build_admin_cost_overview(db=db)
    assert overview["totals"]["total_runs"] == 2
    assert overview["totals"]["failed_runs"] == 1


# ---------- burn rate + projection ----------


def test_burn_rate_uses_trailing_seven_days(db):
    _seed_run_with_events(db, user_id="u1", agent_kind="qualification", events=[
        {"input_tokens": 1_000_000, "output_tokens": 500_000, "model": "gpt-4o-mini"},
    ])
    overview = acs.build_admin_cost_overview(db=db)
    assert overview["burn_rate_per_day_usd"] > 0
    expected = overview["totals"]["total_billable_usd"] / 7.0
    assert abs(overview["burn_rate_per_day_usd"] - expected) < 1e-6


def test_month_projection_is_mtd_plus_burnrate_times_remaining(db):
    _seed_run_with_events(db, user_id="u1", agent_kind="qualification", events=[
        {"input_tokens": 100_000, "output_tokens": 50_000, "model": "gpt-4o-mini"},
    ])
    overview = acs.build_admin_cost_overview(db=db)
    assert overview["projected_month_billable_usd"] >= overview["month_to_date_billable_usd"]


# ---------- expensive runs ----------


def test_expensive_runs_returns_top_ten_when_none_over_threshold(db):
    for i in range(15):
        _seed_run_with_events(db, user_id=f"u{i}", agent_kind="qualification", events=[
            {"input_tokens": 100, "output_tokens": 50},
        ])
    overview = acs.build_admin_cost_overview(db=db)
    assert 1 <= len(overview["expensive_runs"]) <= 10


def test_expensive_runs_returns_runs_over_one_dollar(db):
    _seed_run_with_events(db, user_id="whale", agent_kind="bmc_cost_structure", events=[
        {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "model": "gpt-4o"},
    ])
    overview = acs.build_admin_cost_overview(db=db)
    big = [r for r in overview["expensive_runs"] if r["billable_usd"] >= 1.0]
    assert len(big) >= 1
    assert big[0]["user_id"] == "whale"


# ---------- window clamping ----------


def test_window_days_clamped_to_max(db):
    overview = acs.build_admin_cost_overview(db=db, window_days=10_000)
    assert overview["window_days"] == acs.MAX_WINDOW_DAYS


def test_window_days_clamped_to_min(db):
    overview = acs.build_admin_cost_overview(db=db, window_days=-5)
    assert overview["window_days"] == 1


def test_window_days_default(db):
    overview = acs.build_admin_cost_overview(db=db, window_days=None)
    assert overview["window_days"] == acs.DEFAULT_WINDOW_DAYS


# ---------- cross-user runs listing ----------


def test_cross_user_runs_lists_all_users(db):
    _seed_run_with_events(db, user_id="a", agent_kind="qualification", events=[
        {"input_tokens": 100, "output_tokens": 50},
    ])
    _seed_run_with_events(db, user_id="b", agent_kind="bmc_value_propositions", events=[
        {"input_tokens": 100, "output_tokens": 50},
    ])
    rows = acs.list_recent_runs_cross_user(db=db, limit=10)
    user_ids = {r["user_id"] for r in rows}
    assert user_ids == {"a", "b"}


def test_cross_user_runs_filter_by_status(db):
    _seed_run_with_events(db, user_id="a", agent_kind="qualification", events=[
        {"input_tokens": 100, "output_tokens": 50},
    ])
    _seed_run_with_events(db, user_id="b", agent_kind="qualification", events=[
        {"input_tokens": 100, "output_tokens": 50},
    ], status="failed")
    failed = acs.list_recent_runs_cross_user(db=db, status="failed")
    assert len(failed) == 1
    assert failed[0]["user_id"] == "b"


def test_cross_user_runs_filter_by_kind(db):
    _seed_run_with_events(db, user_id="a", agent_kind="qualification", events=[
        {"input_tokens": 100, "output_tokens": 50},
    ])
    _seed_run_with_events(db, user_id="b", agent_kind="bmc_value_propositions", events=[
        {"input_tokens": 100, "output_tokens": 50},
    ])
    bmc_runs = acs.list_recent_runs_cross_user(db=db, agent_kind="bmc_value_propositions")
    assert len(bmc_runs) == 1
    assert bmc_runs[0]["user_id"] == "b"


# ---------- production-test stats wrapper ----------


def test_production_test_health_proxies_through(db):
    pts.record_test_run(
        db=db,
        payload=pts.TestResultPayload(
            test_name="landing@chromium", status="pass",
        ),
    )
    pts.record_test_run(
        db=db,
        payload=pts.TestResultPayload(
            test_name="auth@chromium", status="fail", error_message="boom",
        ),
    )
    stats = acs.build_production_test_health(db=db, hours=24)
    assert stats["total_runs"] == 2
    assert stats["counts_by_status"]["pass"] == 1
    assert stats["counts_by_status"]["fail"] == 1
