from app.services.canvas.section_base import BaseComponent
from app.utils.logger import logger


# Cost Structure Class
class CostStructure(BaseComponent):
    """
    Represents the cost structure of a business model. Automatically generates
    estimated cost breakdown using AI, while allowing optional manual additions.
    """

    _cost_prompt_template = """
    Given the startup idea: "{idea_description}", create a concise MVP cost worksheet.
    State currency and planning horizon; mark proposed values as assumptions.
    Use Markdown columns: Cost driver | Estimate | Cadence | Basis.
    Include 4 to 6 relevant items. Distinguish one-time, monthly, annual and per-unit
    costs. Label each estimate as supplied, illustrative assumption or quote needed.
    Use TBD where inputs are insufficient, never zero for unknown costs.
    Give separate one-time and monthly subtotals only for numeric rows in the same
    currency, flag incomplete subtotals, and never sum unlike periods or currencies.
    """

    def __init__(self, costs=None):
        super().__init__(costs)

    def generate(self, ai_layer, idea_description):
        """
        Uses the AI layer to generate a cost breakdown based on the idea description.
        This is the primary method used in production.
        """
        logger.info("Generating cost structure using AI layer.")
        prompt = self._cost_prompt_template.format(
            idea_description=idea_description
        )  # Formatting the prompt with the provided idea description
        content = ai_layer.generate_rich_text(
            [{"role": "user", "content": prompt}], format_type="markdown"
        )  # Generating the cost breakdown using the AI layer
        self._value = content  # Updating the cost elements with the generated content
        return self._value

    def add_cost(self, cost):
        # Add a new cost item to the list.
        self._value.append(cost)  # Appending the new cost item to the list of cost elements

    def calculate_total_cost(self):
        """
        Calculates the total cost by summing up all individual costs.
        """
        # Sum up all individual costs to produce the total cost estimate.
        return sum(
            cost.get("amount", 0) for cost in self._value
        )  # Calculating the total cost by summing up the 'amount' of each cost element
