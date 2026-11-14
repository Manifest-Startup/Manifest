"""Tests for the cost-cap enforcement gate (guard_can_run + enforce_cap_or_raise).

Covers:
  - guard returns allowed=True for a fresh user (no usage, default cap)
  - per-agent_kind estimate is used when none is passed
  - explicit est_cost_usd overrides the per-kind default
  - 'paused' reason wins over cap-state reasons
  - 'over_cap' when current spend >= cap
  - 'would_exceed_cap' when current spend + estimate would exceed
  - cap == 0 means no limit (treat as unbounded — only `paused` blocks)
  - enforce_cap_or_raise raises CapBlockedError with structured fields
  - CapBlockedError messages name the cap and current usage
"""

from __future__ import annotations

import pytest

from app.db.database import InMemoryDatabaseClient
from app.services.ai import cost_tracking as cts


@pytest.fixture
def db():
    return InMemoryDatabaseClient()


def _seed_spend(db, *, user_id: str, billable_usd: float):
    """Inject a single cost event so the user's monthly spend is `billable_usd`."""
    run_id = cts.start_agent_run(db=db, user_id=user_id, agent_kind="qualification")
    cts.log_cost_event(
        db=db,
        user_id=user_id,
        agent_kind="qualification",
        model="gpt-4o-mini",
        input_tokens=0,
        output_tokens=0,
        run_id=run_id,
    )
    # Now overwrite the event's billable_cost_usd directly to hit the
    # exact target — the model-based price would be ~$0 for zero tokens.
    db.table("agent_cost_events").update({"billable_cost_usd": billable_usd}).eq(
        "run_id", run_id
    ).execute()
    cts.complete_agent_run(db=db, run_id=run_id, status="complete")


# ---------- guard_can_run ----------


def test_guard_allows_fresh_user(db):
    result = cts.guard_can_run(db=db, user_id="u1", agent_kind="qualification")
    assert result["allowed"] is True
    assert result["reason"] is None
    assert result["monthly_usage_usd"] == 0


def test_guard_uses_per_kind_estimate_when_none_passed(db):
    result = cts.guard_can_run(db=db, user_id="u1", agent_kind="qualification")
    assert result["estimated_cost_usd"] == cts.ESTIMATED_COST_USD_PER_RUN["qualification"]


def test_guard_uses_default_estimate_for_unknown_kind(db):
    result = cts.guard_can_run(db=db, user_id="u1", agent_kind="some_unknown_kind")
    assert result["estimated_cost_usd"] == cts.DEFAULT_ESTIMATED_COST_USD_PER_RUN


def test_guard_explicit_est_overrides_per_kind_default(db):
    result = cts.guard_can_run(
        db=db, user_id="u1", agent_kind="qualification", est_cost_usd=0.50
    )
    assert result["estimated_cost_usd"] == 0.50


def test_guard_paused_blocks_with_paused_reason(db):
    cts.set_user_cost_limits(db=db, user_id="u1", paused=True)
    result = cts.guard_can_run(db=db, user_id="u1", agent_kind="qualification")
    assert result["allowed"] is False
    assert result["reason"] == "paused"


def test_guard_paused_wins_over_cap_state(db):
    # Configure a paused user who is also over cap. paused should be
    # the reason surfaced (more actionable for the operator).
    cts.set_user_cost_limits(db=db, user_id="u1", monthly_variable_cap_usd=10.0, paused=True)
    _seed_spend(db, user_id="u1", billable_usd=15.0)
    result = cts.guard_can_run(db=db, user_id="u1", agent_kind="qualification")
    assert result["allowed"] is False
    assert result["reason"] == "paused"


def test_guard_blocks_when_over_cap(db):
    cts.set_user_cost_limits(db=db, user_id="u1", monthly_variable_cap_usd=10.0)
    _seed_spend(db, user_id="u1", billable_usd=10.01)
    result = cts.guard_can_run(db=db, user_id="u1", agent_kind="qualification")
    assert result["allowed"] is False
    assert result["reason"] == "over_cap"


def test_guard_blocks_when_estimate_would_push_over(db):
    cts.set_user_cost_limits(db=db, user_id="u1", monthly_variable_cap_usd=10.0)
    _seed_spend(db, user_id="u1", billable_usd=9.999)
    # qualification estimate is $0.002 → 9.999 + 0.002 = 10.001 > 10
    result = cts.guard_can_run(db=db, user_id="u1", agent_kind="qualification")
    assert result["allowed"] is False
    assert result["reason"] == "would_exceed_cap"


def test_guard_allows_when_estimate_lands_at_cap(db):
    cts.set_user_cost_limits(db=db, user_id="u1", monthly_variable_cap_usd=10.0)
    _seed_spend(db, user_id="u1", billable_usd=9.998)
    # 9.998 + 0.002 = 10.000 → NOT strictly greater than cap, so allowed.
    # This is the documented behavior — see CapBlockedError docstring.
    result = cts.guard_can_run(db=db, user_id="u1", agent_kind="qualification")
    assert result["allowed"] is True


def test_guard_cap_zero_means_unbounded(db):
    cts.set_user_cost_limits(db=db, user_id="u1", monthly_variable_cap_usd=0.0)
    _seed_spend(db, user_id="u1", billable_usd=999.0)
    # cap=0 is treated as "no cap configured" → only paused can block.
    result = cts.guard_can_run(db=db, user_id="u1", agent_kind="qualification")
    assert result["allowed"] is True


def test_guard_returns_full_payload_shape(db):
    cts.set_user_cost_limits(db=db, user_id="u1", monthly_variable_cap_usd=25.0)
    _seed_spend(db, user_id="u1", billable_usd=5.0)
    result = cts.guard_can_run(db=db, user_id="u1", agent_kind="qualification")
    assert set(result.keys()) == {
        "allowed", "reason", "monthly_usage_usd", "cap_usd",
        "remaining_usd", "estimated_cost_usd", "paused", "agent_kind",
    }
    assert result["monthly_usage_usd"] == 5.0
    assert result["cap_usd"] == 25.0
    assert result["remaining_usd"] == 20.0
    assert result["paused"] is False
    assert result["agent_kind"] == "qualification"


# ---------- enforce_cap_or_raise ----------


def test_enforce_returns_preflight_on_allow(db):
    cts.set_user_cost_limits(db=db, user_id="u1", monthly_variable_cap_usd=25.0)
    result = cts.enforce_cap_or_raise(db=db, user_id="u1", agent_kind="qualification")
    assert result["allowed"] is True
    assert result["reason"] is None


def test_enforce_raises_with_structured_fields(db):
    cts.set_user_cost_limits(db=db, user_id="u1", monthly_variable_cap_usd=10.0)
    _seed_spend(db, user_id="u1", billable_usd=12.0)
    with pytest.raises(cts.CapBlockedError) as exc_info:
        cts.enforce_cap_or_raise(db=db, user_id="u1", agent_kind="qualification")
    err = exc_info.value
    assert err.reason == "over_cap"
    assert err.cap_usd == 10.0
    assert err.monthly_usage_usd == 12.0


def test_cap_blocked_error_messages_are_actionable():
    # paused
    err = cts.CapBlockedError(reason="paused", cap_usd=25.0, monthly_usage_usd=5.0)
    assert "paused" in str(err).lower()
    assert "/account/billing" in str(err)
    # over_cap
    err = cts.CapBlockedError(reason="over_cap", cap_usd=25.0, monthly_usage_usd=30.0)
    assert "$30.00" in str(err)
    assert "$25.00" in str(err)
    # would_exceed_cap
    err = cts.CapBlockedError(reason="would_exceed_cap", cap_usd=25.0, monthly_usage_usd=24.99)
    assert "over your monthly cap" in str(err)
