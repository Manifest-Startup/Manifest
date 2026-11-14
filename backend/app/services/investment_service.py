"""
Investment Service
Handles investments, sweat equity, and cap table management
"""

from datetime import datetime
from typing import Any

from app.utils.logger import logger


class InvestmentService:
    """Service for managing investments and equity in ideas"""

    def __init__(self, db):
        self.db = db
        self.table_name = "investments"
        self.contributions_table = "investment_contributions"
        self.cap_table_name = "cap_table_entries"

    @staticmethod
    def _rows_by_id(rows: Any, key: str) -> dict[str, dict[str, Any]]:
        if not isinstance(rows, list):
            return {}
        return {str(row.get(key)): row for row in rows if row.get(key)}

    def _fetch_users_by_id(self, user_ids: list[str]) -> dict[str, dict[str, Any]]:
        unique_ids = sorted({user_id for user_id in user_ids if user_id})
        if not unique_ids:
            return {}
        response = (
            self.db.table("users")
            .select("user_id, email, first_name, last_name, username, profile_picture_url")
            .in_("user_id", unique_ids)
            .execute()
        )
        return self._rows_by_id(response.data, "user_id")

    def _fetch_ideas_by_id(self, idea_ids: list[str]) -> dict[str, dict[str, Any]]:
        unique_ids = sorted({idea_id for idea_id in idea_ids if idea_id})
        if not unique_ids:
            return {}
        response = (
            self.db.table("ideas")
            .select("idea_id, title, description, created_at, user_id")
            .in_("idea_id", unique_ids)
            .execute()
        )
        return self._rows_by_id(response.data, "idea_id")

    async def create_investment(
        self,
        idea_id: str,
        investor_id: str,
        cash_amount: float = 0,
        sweat_equity_hours: float = 0,
        hourly_rate: float = 50,
        equity_percentage: float = 0,
        investment_type: str = "cash",
        role: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Create a new investment in an idea"""
        sweat_equity_value = sweat_equity_hours * hourly_rate

        investment_data = {
            "idea_id": idea_id,
            "investor_id": investor_id,
            "cash_amount": cash_amount,
            "sweat_equity_hours": sweat_equity_hours,
            "sweat_equity_value": sweat_equity_value,
            "equity_percentage": equity_percentage,
            "investment_type": investment_type,
            "role": role,
            "notes": notes,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            response = (
                self.db.table(self.table_name)
                .upsert(investment_data, on_conflict="idea_id,investor_id")
                .execute()
            )

            if response.data:
                logger.info(
                    f"[InvestmentService] Created investment for idea {idea_id} by {investor_id}"
                )
                await self._update_cap_table(idea_id, investor_id, equity_percentage)
                return response.data
            raise Exception("Failed to create investment")
        except Exception as e:
            logger.error(f"[InvestmentService] Error creating investment: {e}")
            raise

    async def add_contribution(
        self,
        investment_id: str,
        contribution_type: str,
        amount: float = 0,
        hours_worked: float = 0,
        hourly_rate: float = 50,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Add a contribution (cash or sweat) to an existing investment"""
        contribution_data = {
            "investment_id": investment_id,
            "contribution_type": contribution_type,
            "amount": amount if contribution_type == "cash" else hours_worked * hourly_rate,
            "hours_worked": hours_worked,
            "hourly_rate": hourly_rate,
            "description": description,
            "verified": False,
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            response = self.db.table(self.contributions_table).insert(contribution_data).execute()

            if response.data:
                logger.info(
                    f"[InvestmentService] Added {contribution_type} contribution to investment {investment_id}"
                )
                await self._update_investment_totals(investment_id)
                return response.data
            raise Exception("Failed to add contribution")
        except Exception as e:
            logger.error(f"[InvestmentService] Error adding contribution: {e}")
            raise

    async def _update_investment_totals(self, investment_id: str):
        """Recalculate investment totals from all contributions"""
        try:
            contributions = (
                self.db.table(self.contributions_table)
                .select("*")
                .eq("investment_id", investment_id)
                .execute()
            )

            if contributions.data:
                total_cash = sum(
                    c["amount"] for c in contributions.data if c["contribution_type"] == "cash"
                )
                total_sweat_hours = sum(
                    c["hours_worked"]
                    for c in contributions.data
                    if c["contribution_type"] == "sweat"
                )
                total_sweat_value = sum(
                    c["amount"] for c in contributions.data if c["contribution_type"] == "sweat"
                )

                self.db.table(self.table_name).update(
                    {
                        "cash_amount": total_cash,
                        "sweat_equity_hours": total_sweat_hours,
                        "sweat_equity_value": total_sweat_value,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                ).eq("investment_id", investment_id).execute()
        except Exception as e:
            logger.error(f"[InvestmentService] Error updating totals: {e}")

    async def _update_cap_table(self, idea_id: str, stakeholder_id: str, equity_percentage: float):
        """Update or create cap table entry for a stakeholder"""
        cap_entry = {
            "idea_id": idea_id,
            "stakeholder_id": stakeholder_id,
            "stakeholder_type": "user",
            "equity_percentage": equity_percentage,
            "share_class": "common",
            "vesting_status": "none",
            "vested_percentage": 100,
            "updated_at": datetime.utcnow().isoformat(),
        }

        try:
            self.db.table(self.cap_table_name).upsert(
                cap_entry, on_conflict="idea_id,stakeholder_id"
            ).execute()
        except Exception as e:
            logger.error(f"[InvestmentService] Error updating cap table: {e}")

    async def get_investment(self, investment_id: str) -> dict[str, Any] | None:
        """Get a single investment by ID"""
        try:
            response = (
                self.db.table(self.table_name)
                .select("*")
                .eq("investment_id", investment_id)
                .single()
                .execute()
            )
            return response.data
        except Exception:
            return None

    async def get_idea_investments(self, idea_id: str) -> list[dict[str, Any]]:
        """Get all investments for an idea with investor details"""
        try:
            response = (
                self.db.table(self.table_name)
                .select("*")
                .eq("idea_id", idea_id)
                .order("created_at", desc=True)
                .execute()
            )

            investments = response.data or []

            investors_by_id = self._fetch_users_by_id(
                [str(inv.get("investor_id")) for inv in investments if inv.get("investor_id")]
            )

            for inv in investments:
                investor_id = inv.get("investor_id")
                inv["investors"] = investors_by_id.get(str(investor_id), {}) if investor_id else {}

            return investments
        except Exception as e:
            logger.error(f"[InvestmentService] Error getting idea investments: {e}")
            return []

    async def get_user_investments(self, user_id: str) -> list[dict[str, Any]]:
        """Get all investments made by a user (their portfolio)"""
        try:
            response = (
                self.db.table(self.table_name)
                .select("*")
                .eq("investor_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )

            investments = response.data or []

            ideas_by_id = self._fetch_ideas_by_id(
                [str(inv.get("idea_id")) for inv in investments if inv.get("idea_id")]
            )

            for inv in investments:
                inv["ideas"] = ideas_by_id.get(str(inv.get("idea_id")), {})

            return investments
        except Exception as e:
            logger.error(f"[InvestmentService] Error getting user portfolio: {e}")
            return []

    async def get_cap_table(self, idea_id: str) -> list[dict[str, Any]]:
        """Get the full cap table for an idea"""
        try:
            response = (
                self.db.table(self.cap_table_name)
                .select("*")
                .eq("idea_id", idea_id)
                .order("equity_percentage", desc=True)
                .execute()
            )

            entries = response.data or []

            stakeholders_by_id = self._fetch_users_by_id(
                [
                    str(entry.get("stakeholder_id"))
                    for entry in entries
                    if entry.get("stakeholder_id")
                ]
            )

            for entry in entries:
                entry["stakeholder"] = stakeholders_by_id.get(str(entry.get("stakeholder_id")), {})

            return entries
        except Exception as e:
            logger.error(f"[InvestmentService] Error getting cap table: {e}")
            return []

    async def update_investment_status(
        self, investment_id: str, status: str
    ) -> dict[str, Any] | None:
        """Update investment status (pending, confirmed, cancelled)"""
        try:
            response = (
                self.db.table(self.table_name)
                .update({"status": status, "updated_at": datetime.utcnow().isoformat()})
                .eq("investment_id", investment_id)
                .execute()
            )

            if response.data:
                logger.info(
                    f"[InvestmentService] Updated investment {investment_id} status to {status}"
                )
                result = response.data[0] if isinstance(response.data, list) else response.data
                return result
            return None
        except Exception as e:
            logger.error(f"[InvestmentService] Error updating investment status: {e}")
            raise

    async def calculate_sweat_equity(
        self, hours: float, hourly_rate: float = 50, total_valuation: float = 100000
    ) -> dict[str, float]:
        """Calculate sweat equity value and percentage"""
        sweat_value = hours * hourly_rate
        equity_percentage = (sweat_value / total_valuation) * 100 if total_valuation > 0 else 0

        return {
            "sweat_value": sweat_value,
            "equity_percentage": round(equity_percentage, 4),
            "hours": hours,
            "hourly_rate": hourly_rate,
        }


def create_investment_service(db) -> InvestmentService:
    """Factory function to create InvestmentService instance"""
    return InvestmentService(db)
