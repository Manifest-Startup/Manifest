"""GraphQL types and mappers for investments, cap tables, portfolios and sweat equity."""

from datetime import datetime

import strawberry


@strawberry.type
class Investment:
    investment_id: str
    idea_id: str
    investor_id: str
    cash_amount: float
    sweat_equity_hours: float
    sweat_equity_value: float
    equity_percentage: float
    investment_type: str
    role: str | None = None
    status: str = "pending"
    notes: str | None = None
    created_at: datetime
    investor_name: str | None = None
    investor_avatar: str | None = None


@strawberry.type
class CapTableEntry:
    entry_id: str
    idea_id: str
    stakeholder_id: str
    stakeholder_type: str
    equity_percentage: float
    shares_owned: float
    share_class: str
    vesting_status: str
    vested_percentage: float
    stakeholder_name: str | None = None
    stakeholder_avatar: str | None = None


@strawberry.type
class PortfolioItem:
    investment_id: str
    idea_id: str
    idea_title: str
    idea_description: str | None = None
    cash_amount: float
    sweat_equity_value: float
    equity_percentage: float
    status: str
    created_at: datetime


@strawberry.type
class SweatEquityCalculation:
    sweat_value: float
    equity_percentage: float
    hours: float
    hourly_rate: float


@strawberry.input
class CreateInvestmentInput:
    idea_id: str
    cash_amount: float = 0
    sweat_equity_hours: float = 0
    hourly_rate: float = 50
    equity_percentage: float = 0
    investment_type: str = "cash"
    role: str | None = None
    notes: str | None = None


@strawberry.input
class AddContributionInput:
    investment_id: str
    contribution_type: str
    amount: float = 0
    hours_worked: float = 0
    hourly_rate: float = 50
    description: str | None = None
