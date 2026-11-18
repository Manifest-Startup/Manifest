"""GraphQL resolvers for your AI cost dashboard, agent runs and spending caps."""

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.types.costs import (
    AgentRunSummary,
    CostPreflight,
    UserCostDashboard,
    UserCostLimits,
    _map_agent_run,
    _map_cost_dashboard,
)


@strawberry.type
class CostsQuery:
    @strawberry.field
    async def my_cost_dashboard(self, info: strawberry.Info) -> UserCostDashboard:
        """Your AI spend this month, by feature, against your cap."""
        from app.services.ai import cost_tracking as cost_tracking_service

        user_id = get_current_user_id(info.context["request"])
        payload = cost_tracking_service.build_user_cost_dashboard(
            db=info.context["db"], user_id=user_id
        )
        return _map_cost_dashboard(payload)

    @strawberry.field
    async def my_agent_runs(self, info: strawberry.Info, limit: int = 20) -> list[AgentRunSummary]:
        """Your recent AI agent runs with status, cost and duration."""
        from app.services.ai import cost_tracking as cost_tracking_service

        user_id = get_current_user_id(info.context["request"])
        rows = cost_tracking_service.list_recent_runs(
            db=info.context["db"], user_id=user_id, limit=limit
        )
        return [_map_agent_run(r) for r in rows]

    @strawberry.field
    async def my_cost_preflight(
        self,
        info: strawberry.Info,
        agent_kind: str | None = None,
        est_cost_usd: float | None = None,
    ) -> CostPreflight:
        """Preflight check: would a new run be allowed right now?

        Pass `agent_kind` to get the right estimated cost (the guard
        uses a per-kind calibration table). The mutation layer also
        enforces — this is just a UX preview so buttons can be
        disabled before the user clicks.
        """
        from app.services.ai import cost_tracking as cost_tracking_service

        user_id = get_current_user_id(info.context["request"])
        result = cost_tracking_service.guard_can_run(
            db=info.context["db"],
            user_id=user_id,
            agent_kind=agent_kind,
            est_cost_usd=est_cost_usd,
        )
        return CostPreflight(
            allowed=bool(result.get("allowed") or False),
            reason=result.get("reason"),
            monthly_usage_usd=float(result.get("monthly_usage_usd") or 0),
            cap_usd=float(result.get("cap_usd") or 0),
            remaining_usd=float(result.get("remaining_usd") or 0),
            estimated_cost_usd=float(result.get("estimated_cost_usd") or 0),
            paused=bool(result.get("paused") or False),
            agent_kind=result.get("agent_kind"),
        )


@strawberry.type
class CostsMutation:
    @strawberry.mutation
    async def set_variable_cost_cap(
        self,
        info: strawberry.Info,
        monthly_cap_usd: float | None = None,
        paused: bool | None = None,
    ) -> UserCostLimits:
        """Set your monthly AI spend cap in USD, or pause AI spend."""
        from app.services.ai import cost_tracking as cost_tracking_service

        user_id = get_current_user_id(info.context["request"])
        row = cost_tracking_service.set_user_cost_limits(
            db=info.context["db"],
            user_id=user_id,
            monthly_variable_cap_usd=monthly_cap_usd,
            paused=paused,
        )
        return UserCostLimits(
            monthly_variable_cap_usd=float(row.get("monthly_variable_cap_usd") or 0),
            paused=bool(row.get("paused") or False),
            base_subscription_usd=float(row.get("base_subscription_usd") or 0),
            currency=str(row.get("currency") or "USD"),
        )
