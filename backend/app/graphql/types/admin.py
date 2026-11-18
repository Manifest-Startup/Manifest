"""GraphQL types and mappers for admin cost, agent-run and production-test analytics and role changes."""

from typing import Any

import strawberry


@strawberry.type
class AdminDailyCostPoint:
    date: str
    billable_usd: float
    model_cost_usd: float
    event_count: int


@strawberry.type
class AdminUserSpend:
    user_id: str
    email: str | None = None
    billable_usd: float = 0.0
    event_count: int = 0


@strawberry.type
class AdminExpensiveRun:
    id: str
    user_id: str
    user_email: str | None = None
    agent_kind: str
    status: str
    billable_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    started_at: str
    completed_at: str | None = None


@strawberry.type
class AdminCostTotals:
    total_billable_usd: float = 0.0
    total_model_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_runs: int = 0
    failed_runs: int = 0
    active_users: int = 0


@strawberry.type
class AdminLabelSpend:
    """Same shape as CostByLabel but distinct type so admin types
    don't depend on a forward reference to per-user dashboard types."""

    label: str
    billable_usd: float


@strawberry.type
class AdminCostOverview:
    window_days: int
    window_start: str
    generated_at: str
    totals: AdminCostTotals
    burn_rate_per_day_usd: float = 0.0
    month_to_date_billable_usd: float = 0.0
    projected_month_billable_usd: float = 0.0
    daily_series: list[AdminDailyCostPoint]
    top_users: list[AdminUserSpend]
    by_agent_kind: list[AdminLabelSpend]
    by_model: list[AdminLabelSpend]
    expensive_runs: list[AdminExpensiveRun]


@strawberry.type
class AdminAgentRunRow:
    id: str
    user_id: str
    user_email: str | None = None
    agent_kind: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    total_billable_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    error_message: str | None = None
    idea_id: str | None = None
    qualification_session_id: str | None = None


@strawberry.type
class AdminTopFailingTest:
    test_name: str
    failures: int


@strawberry.type
class AdminProductionTestStats:
    window_hours: int
    total_runs: int = 0
    pass_count: int = 0
    fail_count: int = 0
    flaky_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    failure_rate: float = 0.0
    issues_opened: int = 0
    issues_deduped: int = 0
    top_failing_tests: list[AdminTopFailingTest]


def _map_admin_overview(payload: dict[str, Any]) -> AdminCostOverview:
    totals = payload.get("totals") or {}
    return AdminCostOverview(
        window_days=int(payload.get("window_days") or 0),
        window_start=str(payload.get("window_start") or ""),
        generated_at=str(payload.get("generated_at") or ""),
        totals=AdminCostTotals(
            total_billable_usd=float(totals.get("total_billable_usd") or 0),
            total_model_cost_usd=float(totals.get("total_model_cost_usd") or 0),
            total_input_tokens=int(totals.get("total_input_tokens") or 0),
            total_output_tokens=int(totals.get("total_output_tokens") or 0),
            total_runs=int(totals.get("total_runs") or 0),
            failed_runs=int(totals.get("failed_runs") or 0),
            active_users=int(totals.get("active_users") or 0),
        ),
        burn_rate_per_day_usd=float(payload.get("burn_rate_per_day_usd") or 0),
        month_to_date_billable_usd=float(payload.get("month_to_date_billable_usd") or 0),
        projected_month_billable_usd=float(payload.get("projected_month_billable_usd") or 0),
        daily_series=[
            AdminDailyCostPoint(
                date=str(p.get("date") or ""),
                billable_usd=float(p.get("billable_usd") or 0),
                model_cost_usd=float(p.get("model_cost_usd") or 0),
                event_count=int(p.get("event_count") or 0),
            )
            for p in (payload.get("daily_series") or [])
        ],
        top_users=[
            AdminUserSpend(
                user_id=str(u.get("user_id") or ""),
                email=u.get("email"),
                billable_usd=float(u.get("billable_usd") or 0),
                event_count=int(u.get("event_count") or 0),
            )
            for u in (payload.get("top_users") or [])
        ],
        by_agent_kind=[
            AdminLabelSpend(
                label=str(i.get("label") or ""), billable_usd=float(i.get("billable_usd") or 0)
            )
            for i in (payload.get("by_agent_kind") or [])
        ],
        by_model=[
            AdminLabelSpend(
                label=str(i.get("label") or ""), billable_usd=float(i.get("billable_usd") or 0)
            )
            for i in (payload.get("by_model") or [])
        ],
        expensive_runs=[
            AdminExpensiveRun(
                id=str(r.get("id") or ""),
                user_id=str(r.get("user_id") or ""),
                user_email=r.get("user_email"),
                agent_kind=str(r.get("agent_kind") or ""),
                status=str(r.get("status") or ""),
                billable_usd=float(r.get("billable_usd") or 0),
                input_tokens=int(r.get("input_tokens") or 0),
                output_tokens=int(r.get("output_tokens") or 0),
                started_at=str(r.get("started_at") or ""),
                completed_at=r.get("completed_at"),
            )
            for r in (payload.get("expensive_runs") or [])
        ],
    )


def _map_admin_agent_run(row: dict[str, Any]) -> AdminAgentRunRow:
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    return AdminAgentRunRow(
        id=str(row.get("id") or ""),
        user_id=str(row.get("user_id") or ""),
        user_email=row.get("user_email"),
        agent_kind=str(row.get("agent_kind") or ""),
        status=str(row.get("status") or ""),
        started_at=_iso(row.get("started_at")),
        completed_at=_iso(row.get("completed_at")),
        total_billable_cost_usd=float(row.get("total_billable_cost_usd") or 0),
        total_input_tokens=int(row.get("total_input_tokens") or 0),
        total_output_tokens=int(row.get("total_output_tokens") or 0),
        error_message=row.get("error_message"),
        idea_id=row.get("idea_id"),
        qualification_session_id=row.get("qualification_session_id"),
    )


def _map_admin_test_stats(payload: dict[str, Any]) -> AdminProductionTestStats:
    counts = payload.get("counts_by_status") or {}
    return AdminProductionTestStats(
        window_hours=int(payload.get("window_hours") or 0),
        total_runs=int(payload.get("total_runs") or 0),
        pass_count=int(counts.get("pass") or 0),
        fail_count=int(counts.get("fail") or 0),
        flaky_count=int(counts.get("flaky") or 0),
        error_count=int(counts.get("error") or 0),
        skipped_count=int(counts.get("skipped") or 0),
        failure_rate=float(payload.get("failure_rate") or 0),
        issues_opened=int(payload.get("issues_opened") or 0),
        issues_deduped=int(payload.get("issues_deduped") or 0),
        top_failing_tests=[
            AdminTopFailingTest(
                test_name=str(t.get("test_name") or ""),
                failures=int(t.get("failures") or 0),
            )
            for t in (payload.get("top_failing_tests") or [])
        ],
    )
