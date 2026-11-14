from app.services.idea_service import Idea


class DummyAI:
    def generate_summary(self, desc):
        return f"summary:{desc}"


class DummyModel:
    def __init__(self):
        self._ai_layer = DummyAI()

def test_get_summary():
    model = DummyModel()
    idea = Idea(model, "cool idea")
    assert idea.get_summary() == "summary:cool idea"
