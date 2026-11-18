"""The generation worker runs jobs with the owner's key and saves documents on the idea."""

from __future__ import annotations

import threading

from app.services.ai import credentials
from app.workers import generation_worker as worker


class _Rows:
    def __init__(self, data):
        self.data = data


class FakeDb:
    def __init__(self, description="Solar flood sensors"):
        self.description = description

    def table(self, _name):
        return self

    def select(self, *_a):
        return self

    def eq(self, *_a):
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        return _Rows([{"description": self.description}])


def test_single_documents_are_generated_with_the_owner_key_and_saved(monkeypatch):
    seen = {}

    def deck(description):
        seen["key"] = credentials.current_openai_key()
        return f"deck for {description}"

    monkeypatch.setattr(
        worker, "_load_generators", lambda: {"pitch_deck": deck, "prd": lambda d: "prd"}
    )
    monkeypatch.setattr(worker, "_owner_key", lambda job: "sk-owner")
    saved = {}
    from app.services.ideas import document_generation

    monkeypatch.setattr(
        document_generation,
        "_update_idea_documents",
        lambda idea_id, data: saved.update(data, idea=idea_id),
    )
    result = worker.run_job(
        FakeDb(),
        {
            "id": "j",
            "idea_id": "i1",
            "user_id": "u1",
            "document_types": ["pitch_deck", "prd", "nope"],
        },
    )
    assert seen["key"] == "sk-owner"
    assert saved == {
        "pitch_deck": "deck for Solar flood sensors",
        "product_requirements_document": "prd",
        "user_id": "u1",
        "idea": "i1",
    }
    assert result == {"pitch_deck": "saved", "prd": "saved", "nope": "unsupported"}


def test_canvas_jobs_run_the_full_pipeline(monkeypatch):
    calls = []
    from app.services.ideas import document_generation

    monkeypatch.setattr(
        document_generation, "generate_background_tasks", lambda d, i: calls.append((d, i))
    )
    monkeypatch.setattr(worker, "_owner_key", lambda job: None)
    result = worker.run_job(
        FakeDb(),
        {"id": "j", "idea_id": "i1", "user_id": "u1", "document_types": ["business_model_canvas"]},
    )
    assert calls == [("Solar flood sensors", "i1")] and result == {"full_pipeline": "saved"}


def test_loop_stops_and_survives_errors(monkeypatch):
    stop = threading.Event()
    calls = {"n": 0}

    def flaky(db, worker_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db blip")
        stop.set()
        return False

    monkeypatch.setattr(worker, "process_once", flaky)
    worker.run_loop(None, "w", stop, 0.0)
    assert calls["n"] == 2


def test_not_started_under_tests_or_when_disabled(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    assert worker.start_in_background() is False  # PYTEST_CURRENT_TEST is set
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("GENERATION_WORKER_IN_PROCESS", "0")
    assert worker.start_in_background() is False
