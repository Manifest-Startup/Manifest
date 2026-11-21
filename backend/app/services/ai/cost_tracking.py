"""Agent run + LLM cost tracking.

Owns `agent_runs`, `agent_tasks`, `agent_cost_events`, `user_cost_limits`.

Three responsibilities:
  1. Lifecycle: `start_agent_run` / `complete_agent_run` and their
     sub-task siblings.
  2. Cost ingest: read the most recent LLM call's usage from
     `llm_usage_tap`, price it, persist an `agent_cost_events` row, and
     bump the parent run's running totals.
  3. Read APIs: monthly spend, recent runs, per-user cap, used by the
     billing dashboard.

Cap enforcement (blocking new runs at cap) is intentionally NOT in this
slice — see docs/COST_TRACKING.md for the staged rollout plan.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.services.ai.usage_tap import LlmUsage, pop_last_usage
from app.utils.logger import logger

# ---------- pricing ----------

# (input_per_1m_usd, output_per_1m_usd). Source: OpenAI public pricing
# at the time of writing. Keep this list in sync as new models are
# adopted; see docs/COST_TRACKING.md for the update protocol.
PRICING_USD_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o-mini-2024-07-18": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-2024-08-06": (2.50, 10.00),
    "gpt-4o-search-preview": (2.50, 10.00),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1-mini": (3.00, 12.00),
    "o1-preview": (15.00, 60.00),
}

# Unknown model → conservative fallback so we never bill $0 silently.
DEFAULT_PRICING_USD_PER_1M: tuple[float, float] = (1.00, 3.00)

# OpenAI's cached input discount.
CACHED_INPUT_DISCOUNT = 0.5

DEFAULT_MONTHLY_CAP_USD = Decimal("25.00")
DEFAULT_BASE_SUBSCRIPTION_USD = Decimal("49.99")


def _billable_markup() -> float:
    """Multiplier from model cost to user-facing billable cost.

    Default 1.5x. The product never shows the markup directly; we only
    expose the billable value on the dashboard. The model cost stays
    internal.
    """
    try:
        return max(1.0, float(os.getenv("MANIFEST_BILLABLE_MARKUP_FACTOR", "1.5")))
    except (TypeError, ValueError):
        return 1.5


def _compute_model_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> float:
    in_rate, out_rate = PRICING_USD_PER_1M.get(model, DEFAULT_PRICING_USD_PER_1M)
    cached = max(0, min(cached_input_tokens, input_tokens))
    fresh = max(0, input_tokens - cached)
    cost = (
        fresh * in_rate
        + cached * in_rate * CACHED_INPUT_DISCOUNT
        + max(0, output_tokens) * out_rate
    ) / 1_000_000.0
    return round(max(0.0, cost), 6)


# ---------- lifecycle ----------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(response_data: Any) -> dict[str, Any] | None:
    if response_data is None:
        return None
    if isinstance(response_data, list):
        return response_data[0] if response_data else None
    return response_data


def start_agent_run(
    *,
    db,
    user_id: str,
    agent_kind: str,
    idea_id: str | None = None,
    qualification_session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Create an `agent_runs` row in `running` status. Returns the run id."""
    run_id = str(uuid.uuid4())
    payload = {
        "id": run_id,
        "user_id": user_id,
        "agent_kind": agent_kind,
        "status": "running",
        "idea_id": idea_id,
        "qualification_session_id": qualification_session_id,
        "started_at": _now_iso(),
        "total_model_cost_usd": 0,
        "total_external_cost_usd": 0,
        "total_billable_cost_usd": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "metadata": metadata or {},
    }
    try:
        db.table("agent_runs").insert(payload).execute()
    except Exception as exc:
        logger.error(
            "[cost] failed to start agent_run user=%s kind=%s: %s", user_id, agent_kind, exc
        )
        raise
    logger.info("[cost] start_run id=%s user=%s kind=%s", run_id, user_id, agent_kind)
    return run_id


def complete_agent_run(
    *,
    db,
    run_id: str,
    status: str = "complete",
    error_message: str | None = None,
) -> None:
    """Mark a run terminal. Idempotent if the row is already complete."""
    if status not in {"complete", "failed", "cancelled"}:
        raise ValueError(f"invalid terminal status: {status}")
    updates: dict[str, Any] = {
        "status": status,
        "completed_at": _now_iso(),
    }
    if error_message:
        updates["error_message"] = error_message
    try:
        db.table("agent_runs").update(updates).eq("id", run_id).execute()
    except Exception as exc:
        logger.error("[cost] failed to complete agent_run id=%s: %s", run_id, exc)
        raise
    logger.info("[cost] complete_run id=%s status=%s", run_id, status)


def fail_agent_run(*, db, run_id: str, error_message: str) -> None:
    complete_agent_run(db=db, run_id=run_id, status="failed", error_message=error_message)


# ---------- cost ingest ----------


def log_cost_event(
    *,
    db,
    user_id: str,
    agent_kind: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    run_id: str | None = None,
    task_id: str | None = None,
    external_api_cost_usd: float = 0.0,
    note: str | None = None,
) -> dict[str, Any]:
    """Persist one cost event and update the parent run totals.

    Returns the inserted event row (with computed costs) so the caller
    can surface the just-spent amount on the response.
    """
    model_cost = _compute_model_cost_usd(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
    )
    external_cost = max(0.0, float(external_api_cost_usd or 0))
    billable_cost = round((model_cost + external_cost) * _billable_markup(), 6)

    event_id = str(uuid.uuid4())
    event_payload = {
        "id": event_id,
        "user_id": user_id,
        "run_id": run_id,
        "task_id": task_id,
        "agent_kind": agent_kind,
        "model": model,
        "input_tokens": max(0, int(input_tokens or 0)),
        "output_tokens": max(0, int(output_tokens or 0)),
        "cached_input_tokens": max(0, int(cached_input_tokens or 0)),
        "model_cost_usd": model_cost,
        "external_api_cost_usd": external_cost,
        "billable_cost_usd": billable_cost,
        "note": note,
        "created_at": _now_iso(),
    }
    try:
        db.table("agent_cost_events").insert(event_payload).execute()
    except Exception as exc:
        logger.error("[cost] failed to insert cost_event: %s", exc)
        raise

    if run_id:
        _bump_run_totals(db=db, run_id=run_id, event=event_payload)

    logger.info(
        "[cost] event run=%s kind=%s model=%s in=%d out=%d model_cost=%.6f billable=%.6f",
        run_id,
        agent_kind,
        model,
        event_payload["input_tokens"],
        event_payload["output_tokens"],
        model_cost,
        billable_cost,
    )
    return event_payload


def log_cost_event_from_tap(
    *,
    db,
    user_id: str,
    agent_kind: str,
    run_id: str | None = None,
    task_id: str | None = None,
    fallback_model: str | None = None,
    note: str | None = None,
) -> dict[str, Any] | None:
    """Read `llm_usage_tap`'s most recent call and log it.

    Returns the event row, or None if no usage was captured (e.g. the
    LLM call short-circuited or the AI layer is offline). Always clears
    the tap so subsequent reads don't double-count.
    """
    usage: LlmUsage | None = pop_last_usage()
    if usage is None:
        if fallback_model is None:
            return None
        usage = LlmUsage(model=fallback_model)
    return log_cost_event(
        db=db,
        user_id=user_id,
        agent_kind=agent_kind,
        model=usage.model or fallback_model or "unknown",
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        run_id=run_id,
        task_id=task_id,
        note=note,
    )


def _bump_run_totals(*, db, run_id: str, event: dict[str, Any]) -> None:
    """Read-modify-write the parent run's totals.

    Acceptable for v1 because qualification turns are sequential; under
    concurrent fan-out (e.g. BMC section-agents in parallel) this should
    move to a Postgres UPDATE … RETURNING with arithmetic, but the
    in-memory test client doesn't model raw SQL, so we keep it portable.
    """
    try:
        response = db.table("agent_runs").select("*").eq("id", run_id).limit(1).execute()
        rows = response.data or []
        if not rows:
            logger.warning("[cost] cannot bump totals; run not found id=%s", run_id)
            return
        current = dict(rows[0])
        updates = {
            "total_model_cost_usd": float(current.get("total_model_cost_usd") or 0)
            + float(event["model_cost_usd"]),
            "total_external_cost_usd": float(current.get("total_external_cost_usd") or 0)
            + float(event["external_api_cost_usd"]),
            "total_billable_cost_usd": float(current.get("total_billable_cost_usd") or 0)
            + float(event["billable_cost_usd"]),
            "total_input_tokens": int(current.get("total_input_tokens") or 0)
            + int(event["input_tokens"]),
            "total_output_tokens": int(current.get("total_output_tokens") or 0)
            + int(event["output_tokens"]),
        }
        db.table("agent_runs").update(updates).eq("id", run_id).execute()
    except Exception as exc:
        # Aggregation failure must NEVER fail the user-visible request;
        # the canonical totals can be reconstructed from cost_events.
        logger.warning("[cost] bump_run_totals failed id=%s: %s", run_id, exc)


# ---------- user cost limits ----------


def get_user_cost_limits(*, db, user_id: str) -> dict[str, Any]:
    """Return the user's cap row, lazily creating defaults if missing."""
    response = db.table("user_cost_limits").select("*").eq("user_id", user_id).limit(1).execute()
    rows = response.data or []
    if rows:
        return dict(rows[0])
    defaults = {
        "user_id": user_id,
        "monthly_variable_cap_usd": float(DEFAULT_MONTHLY_CAP_USD),
        "paused": False,
        "base_subscription_usd": float(DEFAULT_BASE_SUBSCRIPTION_USD),
        "currency": "USD",
        "updated_at": _now_iso(),
    }
    try:
        db.table("user_cost_limits").insert(defaults).execute()
    except Exception as exc:
        logger.warning("[cost] cost-limit insert failed (likely race), returning defaults: %s", exc)
    return defaults


def set_user_cost_limits(
    *,
    db,
    user_id: str,
    monthly_variable_cap_usd: float | None = None,
    paused: bool | None = None,
) -> dict[str, Any]:
    """Update only the fields the user is allowed to change.

    The base_subscription_usd is admin-controlled and not exposed here.
    """
    current = get_user_cost_limits(db=db, user_id=user_id)
    updates: dict[str, Any] = {"updated_at": _now_iso()}
    if monthly_variable_cap_usd is not None:
        cap = max(0.0, float(monthly_variable_cap_usd))
        # Hard upper bound to prevent typos; admin can raise via env if needed.
        cap_ceiling = float(os.getenv("MANIFEST_USER_CAP_MAX_USD", "5000"))
        updates["monthly_variable_cap_usd"] = min(cap, cap_ceiling)
    if paused is not None:
        updates["paused"] = bool(paused)
    if len(updates) == 1:  # only updated_at — no-op
        return current
    response = db.table("user_cost_limits").update(updates).eq("user_id", user_id).execute()
    row = _row(response.data) or {**current, **updates}
    return dict(row)


# ---------- dashboard queries ----------


def _month_start_iso(now: datetime | None = None) -> str:
    n = now or datetime.now(timezone.utc)
    start = n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start.isoformat()


def _day_bounds_iso(on_date: datetime | None = None) -> tuple[str, str]:
    """[start, end) ISO bounds for the UTC day containing ``on_date``."""
    n = on_date or datetime.now(timezone.utc)
    start = n.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def get_daily_spend(
    *,
    db,
    agent_kind: str | None = None,
    user_id: str | None = None,
    on_date: datetime | None = None,
) -> dict[str, Any]:
    """Aggregate spend for a single UTC day, optionally scoped to an
    ``agent_kind`` and/or ``user_id``.

    Unlike `get_monthly_spend` this is *not* user-scoped by default — the
    autopilot loop runs under a synthetic system identity and needs the
    fleet-wide spend for its own ``agent_kind`` to enforce a daily budget
    cap. ``total_model_cost_usd`` is the real provider spend the budget
    gate enforces against; ``total_billable_usd`` is the marked-up value
    used for user-facing reporting.
    """
    day_start, day_end = _day_bounds_iso(on_date)
    query = (
        db.table("agent_cost_events")
        .select("*")
        .gte("created_at", day_start)
        .lt("created_at", day_end)
    )
    if agent_kind is not None:
        query = query.eq("agent_kind", agent_kind)
    if user_id is not None:
        query = query.eq("user_id", user_id)
    response = query.order("created_at", desc=True).limit(5000).execute()
    events = list(response.data or [])

    total_model = 0.0
    total_billable = 0.0
    total_input = 0
    total_output = 0
    for e in events:
        total_model += float(e.get("model_cost_usd") or 0)
        total_billable += float(e.get("billable_cost_usd") or 0)
        total_input += int(e.get("input_tokens") or 0)
        total_output += int(e.get("output_tokens") or 0)
    return {
        "day_start": day_start,
        "day_end": day_end,
        "agent_kind": agent_kind,
        "total_model_cost_usd": round(total_model, 6),
        "total_billable_usd": round(total_billable, 6),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "event_count": len(events),
    }


def get_monthly_spend(*, db, user_id: str) -> dict[str, Any]:
    """Aggregate the user's current-month spend by kind and by model."""
    month_start = _month_start_iso()
    response = (
        db.table("agent_cost_events")
        .select("*")
        .eq("user_id", user_id)
        .gte("created_at", month_start)
        .order("created_at", desc=True)
        .limit(1000)
        .execute()
    )
    events = list(response.data or [])
    total_billable = 0.0
    total_model = 0.0
    total_input = 0
    total_output = 0
    by_kind: dict[str, float] = {}
    by_model: dict[str, float] = {}
    for e in events:
        billable = float(e.get("billable_cost_usd") or 0)
        total_billable += billable
        total_model += float(e.get("model_cost_usd") or 0)
        total_input += int(e.get("input_tokens") or 0)
        total_output += int(e.get("output_tokens") or 0)
        kind = str(e.get("agent_kind") or "unknown")
        by_kind[kind] = round(by_kind.get(kind, 0.0) + billable, 6)
        model = str(e.get("model") or "unknown")
        by_model[model] = round(by_model.get(model, 0.0) + billable, 6)
    return {
        "month_start": month_start,
        "total_billable_usd": round(total_billable, 6),
        "total_model_cost_usd": round(total_model, 6),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "event_count": len(events),
        "by_agent_kind": by_kind,
        "by_model": by_model,
    }


def list_recent_runs(*, db, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 20), 100))
    response = (
        db.table("agent_runs")
        .select("*")
        .eq("user_id", user_id)
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [dict(r) for r in (response.data or [])]


# ---------- enforcement gate ----------


# Calibrated p50 cost per single run, by agent_kind. Used by the
# guard to decide if a new run would push the user over their monthly
# variable cap. Wildly conservative when unknown — better to require a
# small cap increase than to bill an unsuspecting user.
ESTIMATED_COST_USD_PER_RUN: dict[str, float] = {
    "qualification": 0.002,
    "partner_discovery": 0.005,
    # Grounded web search (search-preview models) plus a structured answer.
    "customer_discovery": 0.03,
    "bmc_customer_segments": 0.004,
    "bmc_value_propositions": 0.004,
    "bmc_channels": 0.004,
    "bmc_customer_relationships": 0.004,
    "bmc_revenue_streams": 0.004,
    "bmc_key_resources": 0.004,
    "bmc_key_activities": 0.004,
    "bmc_key_partners": 0.004,
    "bmc_cost_structure": 0.004,
}
DEFAULT_ESTIMATED_COST_USD_PER_RUN = 0.01


class CapBlockedError(Exception):
    """Raised by `enforce_cap_or_raise` when the caller is at/over cap
    or has paused agents. Resolvers catch this and surface a user-
    visible message rather than a 500.

    The `reason`, `cap_usd`, and `monthly_usage_usd` attributes give the
    UI enough to render an actionable error ("you've used X / Y; raise
    your cap or pause") without re-querying.
    """

    def __init__(self, *, reason: str, cap_usd: float, monthly_usage_usd: float):
        self.reason = reason
        self.cap_usd = cap_usd
        self.monthly_usage_usd = monthly_usage_usd
        super().__init__(self._human_message())

    def _human_message(self) -> str:
        if self.reason == "paused":
            return "Agents are paused for your account. Unpause from /account/billing to continue."
        if self.reason == "over_cap":
            return (
                f"You've reached your monthly variable-cost cap "
                f"(${self.monthly_usage_usd:.2f} / ${self.cap_usd:.2f}). "
                "Raise the cap from /account/billing to continue."
            )
        if self.reason == "would_exceed_cap":
            return (
                f"This run would push you over your monthly cap "
                f"(currently ${self.monthly_usage_usd:.2f} / ${self.cap_usd:.2f}). "
                "Raise the cap from /account/billing to continue."
            )
        return "Agent run blocked by billing policy."


def _estimate_cost_for_kind(agent_kind: str | None) -> float:
    if not agent_kind:
        return DEFAULT_ESTIMATED_COST_USD_PER_RUN
    return ESTIMATED_COST_USD_PER_RUN.get(agent_kind, DEFAULT_ESTIMATED_COST_USD_PER_RUN)


def guard_can_run(
    *,
    db,
    user_id: str,
    agent_kind: str | None = None,
    est_cost_usd: float | None = None,
) -> dict[str, Any]:
    """Read-only preflight: would a new run for this user be allowed?

    Returns a dict the UI can render: ``allowed`` boolean, ``reason``
    ('paused' / 'over_cap' / 'would_exceed_cap' / None), the user's
    current monthly usage, their cap, and the estimate used for the
    decision (so the UI can show "this would cost ~$X").

    Never raises. Callers that want enforcement use ``enforce_cap_or_raise``.
    """
    limits = get_user_cost_limits(db=db, user_id=user_id)
    spend = get_monthly_spend(db=db, user_id=user_id)
    cap = float(limits.get("monthly_variable_cap_usd") or 0)
    used = float(spend.get("total_billable_usd") or 0)
    paused = bool(limits.get("paused") or False)
    estimate = float(
        est_cost_usd if est_cost_usd is not None else _estimate_cost_for_kind(agent_kind)
    )

    reason: str | None = None
    if paused:
        reason = "paused"
    elif cap > 0 and used >= cap:
        reason = "over_cap"
    elif cap > 0 and (used + estimate) > cap:
        reason = "would_exceed_cap"

    return {
        "allowed": reason is None,
        "reason": reason,
        "monthly_usage_usd": round(used, 6),
        "cap_usd": cap,
        "remaining_usd": round(max(0.0, cap - used), 6),
        "estimated_cost_usd": round(estimate, 6),
        "paused": paused,
        "agent_kind": agent_kind,
    }


def enforce_cap_or_raise(
    *,
    db,
    user_id: str,
    agent_kind: str | None = None,
    est_cost_usd: float | None = None,
) -> dict[str, Any]:
    """Call before opening an agent_run. Raises CapBlockedError when
    the user is paused, over cap, or the estimated run would push
    them over.

    Returns the same payload as `guard_can_run` on success so the
    caller can log the estimate against the run for later audit.
    """
    preflight = guard_can_run(
        db=db, user_id=user_id, agent_kind=agent_kind, est_cost_usd=est_cost_usd
    )
    if not preflight["allowed"]:
        logger.info(
            "[cost] blocked user=%s kind=%s reason=%s used=%.4f cap=%.2f",
            user_id,
            agent_kind,
            preflight["reason"],
            preflight["monthly_usage_usd"],
            preflight["cap_usd"],
        )
        raise CapBlockedError(
            reason=str(preflight["reason"]),
            cap_usd=float(preflight["cap_usd"]),
            monthly_usage_usd=float(preflight["monthly_usage_usd"]),
        )
    return preflight


def build_user_cost_dashboard(*, db, user_id: str) -> dict[str, Any]:
    """One-call payload powering the /account/billing page."""
    limits = get_user_cost_limits(db=db, user_id=user_id)
    spend = get_monthly_spend(db=db, user_id=user_id)
    recent = list_recent_runs(db=db, user_id=user_id, limit=20)

    cap = float(limits.get("monthly_variable_cap_usd") or 0)
    used = float(spend["total_billable_usd"])
    remaining = max(0.0, cap - used)
    pct_of_cap = (used / cap * 100.0) if cap > 0 else 0.0
    warn_level = "ok"
    if pct_of_cap >= 100:
        warn_level = "over"
    elif pct_of_cap >= 80:
        warn_level = "critical"
    elif pct_of_cap >= 50:
        warn_level = "elevated"

    return {
        "limits": limits,
        "spend": spend,
        "remaining_usd": round(remaining, 6),
        "pct_of_cap": round(pct_of_cap, 2),
        "warn_level": warn_level,
        "recent_runs": recent,
        "estimated_total_with_subscription_usd": round(
            used + float(limits.get("base_subscription_usd") or 0), 6
        ),
    }
