from app.services.base_component import BaseComponent


class DummyComponent(BaseComponent):
    def __init__(self, desc=""):
        super().__init__(desc)
        self.generated = False

    def _generate(self):
        self.generated = True


def test_update_triggers_generate():
    comp = DummyComponent("idea")
    comp.idea_description = "An idea to test generation"
    comp.update()
    assert comp.generated is True
