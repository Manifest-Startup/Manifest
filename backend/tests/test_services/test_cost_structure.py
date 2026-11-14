from app.services.canvas.cost_structure import CostStructure


def test_add_and_total_cost():
    cs = CostStructure()
    cs.add_cost({"component": "dev", "amount": 100})
    cs.add_cost({"component": "design", "amount": 50})
    assert cs.calculate_total_cost() == 150

    cs.value = [{"component": "marketing", "amount": 200}]
    assert cs.calculate_total_cost() == 200


def test_cost_structure_recursive_json_parsing_like_bmc():
    import json

    from app.services.canvas.business_model_canvas import BusinessModelCanvas

    class DummyAI:
        def generate_rich_text(self, messages, format_type="markdown"):
            # Simulate AI returning a BMC with a stringified cost_structure (with nested stringified JSON)
            return json.dumps(
                {
                    "key_partners": "partners",
                    "cost_structure": json.dumps(
                        {
                            "bottom_up_method": json.dumps(
                                {
                                    "best_case": "Best case details",
                                    "expected_case": "Expected case details",
                                }
                            ),
                            "top_down_method": "Top down details",
                        }
                    ),
                    "revenue_streams": "revenue",
                }
            )

    class DummyIdea:
        def __init__(self, desc):
            self.description = desc

    class DummyModel:
        def __init__(self):
            self.ai_layer = DummyAI()
            self.idea = DummyIdea("idea")

    bmc = BusinessModelCanvas(DummyModel())
    bmc.update()

    # The summary is a string (JSON in this case)
    assert isinstance(bmc.cost_structure.summary, str)

    # The test can parse the summary and then check the contents
    data = json.loads(bmc.cost_structure.summary)
    cost_structure_data = json.loads(data["cost_structure"])
    bottom_up_data = json.loads(cost_structure_data["bottom_up_method"])

    assert bottom_up_data["best_case"] == "Best case details"
    assert cost_structure_data["top_down_method"] == "Top down details"


def test_generate_requests_cost_worksheet_with_explicit_assumptions():
    class CapturingAI:
        def __init__(self):
            self.format_type = None
            self.messages = None

        def generate_rich_text(self, messages, format_type="markdown"):
            self.messages = messages
            self.format_type = format_type
            return "- **Engineering**: $12,000 to $18,000 one-time for MVP development."

    ai = CapturingAI()
    cs = CostStructure()

    result = cs.generate(ai, "AI-powered manufacturing workflow planner")

    assert result == "- **Engineering**: $12,000 to $18,000 one-time for MVP development."
    assert ai.format_type == "markdown"
    assert ai.messages is not None
    prompt = ai.messages[0]["content"]
    assert "Cost driver | Estimate | Cadence | Basis" in prompt
    assert "one-time, monthly, annual and per-unit" in prompt
    assert "TBD" in prompt
    assert "never sum unlike periods or currencies" in prompt
