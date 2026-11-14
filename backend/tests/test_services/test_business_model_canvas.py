import json

from app.services.business_model_canvas_service import BusinessModelCanvas


class DummyAI:
    def generate_rich_text(self, messages, format_type="markdown"):
        return json.dumps(
            {
                "key_partners": "partners",
                "key_activities": "activities",
                "key_resources": "resources",
                "value_propositions": "values",
                "customer_relationships": "relationships",
                "channels": "channels",
                "customer_segments": "segments",
                "cost_structure": "costs",
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


def test_update_generates_components():
    model = DummyModel()
    bmc = BusinessModelCanvas(model)
    bmc.update()

    assert bmc.key_partners.summary is not None
    assert bmc.key_resources.summary is not None
    assert bmc.cost_structure.summary is not None
    assert bmc.revenue_streams.summary is not None

    assert isinstance(bmc.summary, str)
    data = json.loads(bmc.summary)
    assert data["key_partners"] == "partners"


def test_cost_structure_plain_object():
    from app.services.business_model_canvas_service import BusinessModelCanvas

    class DummyModel:
        pass

    bmc = BusinessModelCanvas(DummyModel())
    bmc._cost_structure.summary = {"foo": "bar"}
    assert isinstance(bmc._cost_structure.summary, dict)
    assert bmc._cost_structure.summary["foo"] == "bar"


def test_cost_structure_stringified_json():
    import json

    from app.services.business_model_canvas_service import BusinessModelCanvas

    class DummyModel:
        pass

    bmc = BusinessModelCanvas(DummyModel())
    stringified = json.dumps({"foo": "bar"})

    def try_parse_json(val):
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    return {k: try_parse_json(v) for k, v in parsed.items()}
                return parsed
            except Exception:
                return val
        elif isinstance(val, dict):
            return {k: try_parse_json(v) for k, v in val.items()}
        return val

    cost_structure = try_parse_json(stringified)
    bmc._cost_structure.summary = cost_structure
    assert isinstance(bmc._cost_structure.summary, dict)
    assert bmc._cost_structure.summary["foo"] == "bar"


def test_cost_structure_nested_stringified_json():
    import json

    from app.services.business_model_canvas_service import BusinessModelCanvas

    class DummyModel:
        pass

    bmc = BusinessModelCanvas(DummyModel())
    nested = {"bar": json.dumps({"baz": 123})}
    stringified = json.dumps(nested)

    def try_parse_json(val):
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    return {k: try_parse_json(v) for k, v in parsed.items()}
                return parsed
            except Exception:
                return val
        elif isinstance(val, dict):
            return {k: try_parse_json(v) for k, v in val.items()}
        return val

    cost_structure = try_parse_json(stringified)
    bmc._cost_structure.summary = cost_structure
    assert isinstance(bmc._cost_structure.summary, dict)
    assert isinstance(bmc._cost_structure.summary["bar"], dict)
    assert bmc._cost_structure.summary["bar"]["baz"] == 123


def test_cost_structure_invalid_json():
    from app.services.business_model_canvas_service import BusinessModelCanvas

    class DummyModel:
        pass

    bmc = BusinessModelCanvas(DummyModel())
    invalid = "not a json"

    def try_parse_json(val):
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    return {k: try_parse_json(v) for k, v in parsed.items()}
                return parsed
            except Exception:
                return val
        elif isinstance(val, dict):
            return {k: try_parse_json(v) for k, v in val.items()}
        return val

    cost_structure = try_parse_json(invalid)
    bmc._cost_structure.summary = cost_structure
    assert isinstance(bmc._cost_structure.summary, str)
    assert bmc._cost_structure.summary == "not a json"


def test_business_model_canvas_prompt_requests_cost_worksheet():
    class PromptCapturingAI:
        def __init__(self):
            self.messages = None

        def generate_rich_text(self, messages, format_type="markdown"):
            self.messages = messages
            return """# Key Partners
- Supplier network
# Key Activities
- Build product
# Key Resources
- Engineering team
# Value Propositions
- Faster workflows
# Customer Relationships
- High-touch onboarding
# Channels
- Founder-led sales
# Customer Segments
- Operations teams
# Cost Structure
- **Manufacturing Costs**: $45,000 to $70,000 one-time for tooling and raw materials.
- **Estimated MVP Cost Range**: $90,000 to $140,000.
# Revenue Streams
- Subscription"""

    class PromptModel:
        def __init__(self):
            self.ai_layer = PromptCapturingAI()
            self.idea = DummyIdea("Industrial IoT water monitoring platform")

    model = PromptModel()
    bmc = BusinessModelCanvas(model)
    bmc.update()

    assert model.ai_layer.messages is not None
    user_prompt = model.ai_layer.messages[1]["content"]
    assert "# Cost Structure" in user_prompt
    assert "Cost driver | Estimate | Cadence | Basis" in user_prompt
    assert "Use TBD" in user_prompt
    assert "one-time, monthly, annual, or per-unit" in user_prompt
