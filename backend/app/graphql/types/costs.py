"""GraphQL types and mappers for your AI cost dashboard, agent runs and spending caps."""

from typing import Any

import strawberry


@strawberry.type
class AgentRunSummary:
    id: str
    agent_kind: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    total_model_cost_usd: float = 0.0
    total_billable_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    error_message: str | None = None
    qualification_session_id: str | None = None
    idea_id: str | None = None


@strawberry.type
class CostByLabel:
    label: str
    billable_usd: float


@strawberry.type
class MonthlySpend:
    month_start: str
    total_billable_usd: float
    total_model_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    event_count: int
    by_agent_kind: list[CostByLabel]
    by_model: list[CostByLabel]


@strawberry.type
class UserCostLimits:
    monthly_variable_cap_usd: float
    paused: bool
    base_subscription_usd: float
    currency: str = "USD"


@strawberry.type
class CostPreflight:
    """Read-only preflight: would a new agent run be allowed right now?

    The frontend calls this to know whether to disable an agent
    button before the user clicks it; the resolver layer ALSO enforces
    on every agent mutation, so this is purely a UX preview.
    """

    allowed: bool
    reason: str | None = None  # 'paused' | 'over_cap' | 'would_exceed_cap' | null
    monthly_usage_usd: float
    cap_usd: float
    remaining_usd: float
    estimated_cost_usd: float
    paused: bool
    agent_kind: str | None = None


@strawberry.type
class UserCostDashboard:
    limits: UserCostLimits
    spend: MonthlySpend
    remaining_usd: float
    pct_of_cap: float
    warn_level: str  # ok | elevated | critical | over
    recent_runs: list[AgentRunSummary]
    estimated_total_with_subscription_usd: float


def _map_agent_run(row: dict[str, Any]) -> AgentRunSummary:
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    return AgentRunSummary(
        id=str(row.get("id", "")),
        agent_kind=str(row.get("agent_kind", "")),
        status=str(row.get("status", "")),
        started_at=_iso(row.get("started_at")),
        completed_at=_iso(row.get("completed_at")),
        total_model_cost_usd=float(row.get("total_model_cost_usd") or 0),
        total_billable_cost_usd=float(row.get("total_billable_cost_usd") or 0),
        total_input_tokens=int(row.get("total_input_tokens") or 0),
        total_output_tokens=int(row.get("total_output_tokens") or 0),
        error_message=row.get("error_message"),
        qualification_session_id=row.get("qualification_session_id"),
        idea_id=row.get("idea_id"),
    )


def _map_cost_dashboard(payload: dict[str, Any]) -> UserCostDashboard:
    limits = payload.get("limits") or {}
    spend = payload.get("spend") or {}
    return UserCostDashboard(
        limits=UserCostLimits(
            monthly_variable_cap_usd=float(limits.get("monthly_variable_cap_usd") or 0),
            paused=bool(limits.get("paused") or False),
            base_subscription_usd=float(limits.get("base_subscription_usd") or 0),
            currency=str(limits.get("currency") or "USD"),
        ),
        spend=MonthlySpend(
            month_start=str(spend.get("month_start") or ""),
            total_billable_usd=float(spend.get("total_billable_usd") or 0),
            total_model_cost_usd=float(spend.get("total_model_cost_usd") or 0),
            total_input_tokens=int(spend.get("total_input_tokens") or 0),
            total_output_tokens=int(spend.get("total_output_tokens") or 0),
            event_count=int(spend.get("event_count") or 0),
            by_agent_kind=[
                CostByLabel(label=k, billable_usd=float(v))
                for k, v in (spend.get("by_agent_kind") or {}).items()
            ],
            by_model=[
                CostByLabel(label=k, billable_usd=float(v))
                for k, v in (spend.get("by_model") or {}).items()
            ],
        ),
        remaining_usd=float(payload.get("remaining_usd") or 0),
        pct_of_cap=float(payload.get("pct_of_cap") or 0),
        warn_level=str(payload.get("warn_level") or "ok"),
        recent_runs=[_map_agent_run(r) for r in (payload.get("recent_runs") or [])],
        estimated_total_with_subscription_usd=float(
            payload.get("estimated_total_with_subscription_usd") or 0
        ),
    )
