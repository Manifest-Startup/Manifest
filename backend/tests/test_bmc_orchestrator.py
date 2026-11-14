"""Tests for bmc_orchestrator_service.

Covers:
  - section validation (unknown name rejected)
  - canonical order in get_sections
  - placeholder rows when no sections exist yet
  - regenerate_section: opens + closes a cost-tracked agent_run,
    logs a cost event via the LLM usage tap, upserts the row
  - regenerate_section: fails the agent_run on LLM error
  - regenerate_section: requires the idea to have a description
  - regenerate_all_sections: 9 runs in canonical order, later
    sections see earlier sections as sibling context
  - siblings are passed into the LLM prompt
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.db.database import InMemoryDatabaseClient
from app.services.canvas import orchestrator as bmc
from app.services.ai import usage_tap as llm_usage_tap


@pytest.fixture
def db():
    inmem = InMemoryDatabaseClient()
    # Seed an idea so the service can fetch its description.
    inmem.table("ideas").insert({
        "idea_id": "idea-1",
        "user_id": "u1",
        "title": "Marketplace for indie game soundtracks",
        "description": "An online marketplace where indie game devs license original soundtracks from independent composers.",
    }).execute()
    return inmem


@pytest.fixture
def ai_layer():
    layer = MagicMock()
    layer.is_available.return_value = True
    return layer


def _stub_llm_response(*, content: str = "Indie game devs and small studios.", needs_review: bool = False):
    """Return a function suitable as ai_layer.generate_structured_response.side_effect
    that also writes a usage entry into the tap (mirrors what the AIRouter does)."""
    def _call(messages, *args, **kwargs):
        llm_usage_tap.set_last_usage(
            "gpt-4o-mini",
            {"prompt_tokens": 800, "completion_tokens": 200},
        )
        return {
            "section_name": "customer_segments",
            "content": content,
            "needs_user_review": needs_review,
            "rationale": "test",
        }
    return _call


# ---------- validation ----------


def test_regenerate_rejects_unknown_section(db, ai_layer):
    with pytest.raises(bmc.BmcSectionError):
        bmc.regenerate_section(
            db=db, ai_layer=ai_layer,
            user_id="u1", idea_id="idea-1",
            section_name="not_a_real_section",
        )


def test_regenerate_rejects_idea_without_description(db, ai_layer):
    db.table("ideas").insert({
        "idea_id": "idea-empty",
        "user_id": "u1",
        "title": "Empty",
        "description": "   ",
    }).execute()
    with pytest.raises(bmc.BmcSectionError):
        bmc.regenerate_section(
            db=db, ai_layer=ai_layer,
            user_id="u1", idea_id="idea-empty",
            section_name="customer_segments",
        )


def test_regenerate_requires_available_ai_layer(db):
    layer = MagicMock()
    layer.is_available.return_value = False
    with pytest.raises(bmc.BmcSectionError):
        bmc.regenerate_section(
            db=db, ai_layer=layer,
            user_id="u1", idea_id="idea-1",
            section_name="customer_segments",
        )


# ---------- get_sections ----------


def test_get_sections_returns_nine_placeholders_when_empty(db):
    rows = bmc.get_sections(db=db, idea_id="idea-1")
    assert len(rows) == 9
    assert [r["section_name"] for r in rows] == list(bmc.SECTION_NAMES)
    assert all(r["content"] is None for r in rows)


def test_get_sections_preserves_canonical_order(db):
    # Insert a section out of canonical order — the service must still
    # return them in canonical order.
    db.table(bmc.TABLE).insert({
        "id": "bmc-1",
        "idea_id": "idea-1",
        "section_name": "key_partners",
        "content": "Stripe, Slack",
        "content_format": "markdown",
        "needs_user_review": False,
    }).execute()
    rows = bmc.get_sections(db=db, idea_id="idea-1")
    assert [r["section_name"] for r in rows] == list(bmc.SECTION_NAMES)
    assert rows[bmc.SECTION_NAMES.index("key_partners")]["content"] == "Stripe, Slack"


# ---------- regenerate happy path ----------


def test_regenerate_section_persists_row_and_logs_cost(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_llm_response(
        content="Customer segments: indie game devs (10K studios).",
    )
    row = bmc.regenerate_section(
        db=db, ai_layer=ai_layer,
        user_id="u1", idea_id="idea-1",
        section_name="customer_segments",
    )
    assert row["section_name"] == "customer_segments"
    assert "indie game devs" in row["content"]

    # Cost event was logged for the LLM call
    events = db.table("agent_cost_events").select("*").eq("user_id", "u1").execute().data
    assert len(events) == 1
    assert events[0]["agent_kind"] == "bmc_customer_segments"
    assert events[0]["input_tokens"] == 800
    assert events[0]["output_tokens"] == 200

    # agent_run is complete
    runs = db.table("agent_runs").select("*").eq("user_id", "u1").execute().data
    assert len(runs) == 1
    assert runs[0]["status"] == "complete"
    assert runs[0]["agent_kind"] == "bmc_customer_segments"


def test_regenerate_section_sets_needs_user_review_flag(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_llm_response(
        content="Picked a specific niche", needs_review=True,
    )
    row = bmc.regenerate_section(
        db=db, ai_layer=ai_layer,
        user_id="u1", idea_id="idea-1",
        section_name="customer_segments",
    )
    assert row["needs_user_review"] is True


def test_regenerate_section_marks_run_failed_on_llm_error(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = RuntimeError("LLM crashed")
    with pytest.raises(bmc.BmcSectionError):
        bmc.regenerate_section(
            db=db, ai_layer=ai_layer,
            user_id="u1", idea_id="idea-1",
            section_name="customer_segments",
        )
    runs = db.table("agent_runs").select("*").eq("user_id", "u1").execute().data
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert runs[0]["error_message"]


def test_regenerate_section_rejects_empty_llm_content(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_llm_response(content="  ")
    with pytest.raises(bmc.BmcSectionError):
        bmc.regenerate_section(
            db=db, ai_layer=ai_layer,
            user_id="u1", idea_id="idea-1",
            section_name="customer_segments",
        )


# ---------- siblings ----------


def test_later_sections_see_earlier_sections_as_siblings(db, ai_layer):
    # First generation: customer_segments with distinctive content.
    ai_layer.generate_structured_response.side_effect = _stub_llm_response(
        content="Indie game devs and small studios building narrative games.",
    )
    bmc.regenerate_section(
        db=db, ai_layer=ai_layer,
        user_id="u1", idea_id="idea-1",
        section_name="customer_segments",
    )

    # Second generation: value_propositions. We capture the messages
    # passed to the LLM and confirm the customer_segments content is
    # in the prompt as a sibling.
    captured_messages: list = []

    def _capture(messages, *args, **kwargs):
        captured_messages.extend(messages)
        llm_usage_tap.set_last_usage("gpt-4o-mini", {"prompt_tokens": 200, "completion_tokens": 100})
        return {
            "section_name": "value_propositions",
            "content": "Royalty-free licensing in 60s",
            "needs_user_review": False,
        }
    ai_layer.generate_structured_response.side_effect = _capture

    bmc.regenerate_section(
        db=db, ai_layer=ai_layer,
        user_id="u1", idea_id="idea-1",
        section_name="value_propositions",
    )
    user_block = next(m["content"] for m in captured_messages if m["role"] == "user")
    assert "narrative games" in user_block, "earlier sibling section must be in the prompt"


def test_regenerate_all_creates_runs_for_each_section(db, ai_layer):
    counter = {"i": 0}

    def _per_call(messages, *args, **kwargs):
        counter["i"] += 1
        llm_usage_tap.set_last_usage("gpt-4o-mini", {"prompt_tokens": 100, "completion_tokens": 50})
        return {
            "section_name": "x",
            "content": f"content {counter['i']}",
            "needs_user_review": False,
        }
    ai_layer.generate_structured_response.side_effect = _per_call

    rows = bmc.regenerate_all_sections(
        db=db, ai_layer=ai_layer,
        user_id="u1", idea_id="idea-1",
    )
    assert len(rows) == 9
    runs = db.table("agent_runs").select("*").eq("user_id", "u1").execute().data
    assert len(runs) == 9
    kinds = sorted(r["agent_kind"] for r in runs)
    assert kinds == sorted(f"bmc_{n}" for n in bmc.SECTION_NAMES)


def test_regenerate_all_continues_after_section_failure(db, ai_layer):
    """One section blowing up should NOT abort the whole canvas."""
    call_count = {"n": 0}

    def _flaky(messages, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("transient LLM hiccup")
        llm_usage_tap.set_last_usage("gpt-4o-mini", {"prompt_tokens": 100, "completion_tokens": 50})
        return {
            "section_name": "x",
            "content": f"call {call_count['n']}",
            "needs_user_review": False,
        }
    ai_layer.generate_structured_response.side_effect = _flaky

    rows = bmc.regenerate_all_sections(
        db=db, ai_layer=ai_layer,
        user_id="u1", idea_id="idea-1",
    )
    # 8 successes, 1 failure recorded
    assert len(rows) == 8
    runs = db.table("agent_runs").select("*").eq("user_id", "u1").execute().data
    statuses = [r["status"] for r in runs]
    assert statuses.count("failed") == 1
    assert statuses.count("complete") == 8
