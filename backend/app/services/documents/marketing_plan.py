from app.utils.auto_property import AutoProperty
from app.utils.logger import logger


class MarketingPlan:
    def __init__(self, model, **kwargs):
        logger.info(
            "MarketingPlan Object created."
        )  # Log the creation of a new MarketingPlan object
        self.model = model
        self._product_name = kwargs.get("product_name")  # Initialize product_name from kwargs
        self._year = kwargs.get("year")  # Initialize year from kwargs
        self._target_markets = []  # Initialize empty list for target markets
        self._objectives = []  # Initialize empty list for objectives
        self._strategies = []  # Initialize empty list for strategies
        self._tactics = []  # Initialize empty list for tactics
        self._budget = 0.0  # Initialize budget to 0.0
        self._kpis = []  # Initialize empty list for KPIs

    product_name = AutoProperty("product_name")
    year = AutoProperty("year")
    target_markets = AutoProperty("target_markets")
    objectives = AutoProperty("objectives")
    strategies = AutoProperty("strategies")
    tactics = AutoProperty("tactics")
    budget = AutoProperty("budget")
    kpis = AutoProperty("kpis")

    def add_target_market(self, market_segment):
        logger.info(
            f"Adding target market: {market_segment}"
        )  # Log when a new target market is added
        self._target_markets.append(market_segment)

    def add_objective(self, objective):
        logger.info(f"Adding objective: {objective}")  # Log when a new objective is added
        self._objectives.append(objective)

    def add_strategy(self, strategy):
        logger.info(f"Adding strategy: {strategy}")  # Log when a new strategy is added
        self._strategies.append(strategy)

    def add_tactic(self, tactic):
        logger.info(f"Adding tactic: {tactic}")  # Log when a new tactic is added
        self._tactics.append(tactic)

    def set_budget(self, amount):
        if amount < 0:
            logger.warning(
                "Attempted to set a negative budget."
            )  # Log a warning if an attempt is made to set a negative budget
            return "Budget amount must be non-negative."
        self._budget = amount
        logger.info(f"Budget set to: ${self._budget:,.2f}")  # Log when budget is set
        return f"Budget set to ${self._budget:,.2f}"

    def add_kpi(self, kpi):
        logger.info(f"Adding KPI: {kpi}")  # Log when a new KPI is added
        self._kpis.append(kpi)

    def display_plan(self):
        logger.info(
            f"=== Marketing Plan for {self.product_name} ({self.year}) ==="
        )  # Log the display of the marketing plan
        logger.info("\nTarget Markets:")
        for market in self.target_markets:
            logger.info(f"  - {market}")

        logger.info("\nObjectives:")
        for obj in self.objectives:
            logger.info(f"  - {obj}")

        logger.info("\nStrategies:")
        for strategy in self.strategies:
            logger.info(f"  - {strategy}")

        logger.info("\nTactics:")
        for tactic in self.tactics:
            logger.info(f"  - {tactic}")

        logger.info(f"\nBudget: ${self.budget:,.2f}")  # Log the budget

        logger.info("\nKey Performance Indicators (KPIs):")
        for kpi in self.kpis:
            logger.info(f"  - {kpi}")

    def get_total_budget(self):
        return self._budget  # Return the total budget
