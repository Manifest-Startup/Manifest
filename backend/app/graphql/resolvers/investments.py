"""GraphQL resolvers for investments, cap tables, portfolios and sweat equity."""

from datetime import datetime

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.resolvers.shared import _display_name, _require_full_account
from app.graphql.types.investments import (
    AddContributionInput,
    CapTableEntry,
    CreateInvestmentInput,
    Investment,
    PortfolioItem,
    SweatEquityCalculation,
)


@strawberry.type
class InvestmentsQuery:
    @strawberry.field
    async def idea_investments(self, info: strawberry.Info, idea_id: str) -> list[Investment]:
        """Get all investments for an idea"""
        from app.services.social.investments import create_investment_service

        service = create_investment_service(info.context["db"])
        investments_data = await service.get_idea_investments(idea_id)

        investments = []
        for inv in investments_data:
            investor = inv.get("investors", {}) or {}
            investments.append(
                Investment(
                    investment_id=inv["investment_id"],
                    idea_id=inv["idea_id"],
                    investor_id=inv["investor_id"],
                    cash_amount=float(inv.get("cash_amount") or 0),
                    sweat_equity_hours=float(inv.get("sweat_equity_hours") or 0),
                    sweat_equity_value=float(inv.get("sweat_equity_value") or 0),
                    equity_percentage=float(inv.get("equity_percentage") or 0),
                    investment_type=inv.get("investment_type") or "cash",
                    role=inv.get("role"),
                    status=inv.get("status") or "pending",
                    notes=inv.get("notes"),
                    created_at=(
                        datetime.fromisoformat(inv["created_at"].replace("Z", "+00:00"))
                        if isinstance(inv["created_at"], str)
                        else inv["created_at"]
                    ),
                    investor_name=_display_name(investor),
                    investor_avatar=investor.get("profile_picture_url"),
                )
            )
        return investments

    @strawberry.field
    async def idea_cap_table(self, info: strawberry.Info, idea_id: str) -> list[CapTableEntry]:
        """Get the cap table for an idea"""
        from app.services.social.investments import create_investment_service

        service = create_investment_service(info.context["db"])
        cap_data = await service.get_cap_table(idea_id)

        entries = []
        for entry in cap_data:
            stakeholder = entry.get("stakeholder", {}) or {}
            entries.append(
                CapTableEntry(
                    entry_id=entry["entry_id"],
                    idea_id=entry["idea_id"],
                    stakeholder_id=entry["stakeholder_id"],
                    stakeholder_type=entry.get("stakeholder_type") or "user",
                    equity_percentage=float(entry.get("equity_percentage") or 0),
                    shares_owned=float(entry.get("shares_owned") or 0),
                    share_class=entry.get("share_class") or "common",
                    vesting_status=entry.get("vesting_status") or "none",
                    vested_percentage=float(entry.get("vested_percentage") or 100),
                    stakeholder_name=_display_name(stakeholder),
                    stakeholder_avatar=stakeholder.get("profile_picture_url"),
                )
            )
        return entries

    @strawberry.field
    async def my_portfolio(self, info: strawberry.Info) -> list[PortfolioItem]:
        """Get current user's investment portfolio"""
        user_id = get_current_user_id(info.context["request"])
        from app.services.social.investments import create_investment_service

        service = create_investment_service(info.context["db"])
        portfolio_data = await service.get_user_investments(user_id)

        items = []
        for inv in portfolio_data:
            idea = inv.get("ideas", {}) or {}
            items.append(
                PortfolioItem(
                    investment_id=inv["investment_id"],
                    idea_id=inv["idea_id"],
                    idea_title=idea.get("title") or "Untitled Idea",
                    idea_description=idea.get("description"),
                    cash_amount=float(inv.get("cash_amount") or 0),
                    sweat_equity_value=float(inv.get("sweat_equity_value") or 0),
                    equity_percentage=float(inv.get("equity_percentage") or 0),
                    status=inv.get("status") or "pending",
                    created_at=(
                        datetime.fromisoformat(inv["created_at"].replace("Z", "+00:00"))
                        if isinstance(inv["created_at"], str)
                        else inv["created_at"]
                    ),
                )
            )
        return items

    @strawberry.field
    async def calculate_sweat_equity(
        self, hours: float, hourly_rate: float = 50, total_valuation: float = 100000
    ) -> SweatEquityCalculation:
        """Calculate sweat equity value and percentage"""
        sweat_value = hours * hourly_rate
        equity_percentage = (sweat_value / total_valuation) * 100 if total_valuation > 0 else 0

        return SweatEquityCalculation(
            sweat_value=sweat_value,
            equity_percentage=round(equity_percentage, 4),
            hours=hours,
            hourly_rate=hourly_rate,
        )


@strawberry.type
class InvestmentsMutation:
    @strawberry.mutation
    async def create_investment(
        self, info: strawberry.Info, input: CreateInvestmentInput
    ) -> Investment:
        """Create a new investment in an idea"""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        from app.services.social.investments import create_investment_service

        service = create_investment_service(info.context["db"])

        result = await service.create_investment(
            idea_id=input.idea_id,
            investor_id=user_id,
            cash_amount=input.cash_amount,
            sweat_equity_hours=input.sweat_equity_hours,
            hourly_rate=input.hourly_rate,
            equity_percentage=input.equity_percentage,
            investment_type=input.investment_type,
            role=input.role,
            notes=input.notes,
        )

        return Investment(
            investment_id=result["investment_id"],
            idea_id=result["idea_id"],
            investor_id=result["investor_id"],
            cash_amount=float(result.get("cash_amount") or 0),
            sweat_equity_hours=float(result.get("sweat_equity_hours") or 0),
            sweat_equity_value=float(result.get("sweat_equity_value") or 0),
            equity_percentage=float(result.get("equity_percentage") or 0),
            investment_type=result.get("investment_type") or "cash",
            role=result.get("role"),
            status=result.get("status") or "pending",
            notes=result.get("notes"),
            created_at=(
                datetime.fromisoformat(result["created_at"].replace("Z", "+00:00"))
                if isinstance(result["created_at"], str)
                else result["created_at"]
            ),
        )

    @strawberry.mutation
    async def add_investment_contribution(
        self, info: strawberry.Info, input: AddContributionInput
    ) -> bool:
        """Add a contribution to an existing investment"""
        _require_full_account(info.context["db"], info.context["request"])
        from app.services.social.investments import create_investment_service

        service = create_investment_service(info.context["db"])

        await service.add_contribution(
            investment_id=input.investment_id,
            contribution_type=input.contribution_type,
            amount=input.amount,
            hours_worked=input.hours_worked,
            hourly_rate=input.hourly_rate,
            description=input.description,
        )
        return True

    @strawberry.mutation
    async def update_investment_status(
        self, info: strawberry.Info, investment_id: str, status: str
    ) -> bool:
        """Update the status of an investment (pending, confirmed, cancelled)"""
        _require_full_account(info.context["db"], info.context["request"])
        from app.services.social.investments import create_investment_service

        service = create_investment_service(info.context["db"])

        await service.update_investment_status(investment_id, status)
        return True
