"""Tests for partner_discovery_service.

Covers:
  - validation (idea must have description; ai_layer must be available)
  - LLM happy path: persists candidates, logs cost event, closes run
  - normalization rules (drop malformed entries; clamp enums; dedupe by name)
  - ranking (highest relevance_score gets rank=1)
  - upsert dedupe: re-running on the same idea updates rows, no dupes
  - approval flag round-trip
  - run is marked failed on LLM error
  - threads existing key_partners section into the prompt
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.db.database import InMemoryDatabaseClient
from app.services.ai import usage_tap as llm_usage_tap
from app.services.ideas import partner_discovery as pd


@pytest.fixture
def db():
    inmem = InMemoryDatabaseClient()
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


def _stub_candidates_response(candidates):
    """Return an LLM stub that writes usage to the tap + returns these candidates."""
    def _call(messages, *args, **kwargs):
        llm_usage_tap.set_last_usage(
            "gpt-4o-mini",
            {"prompt_tokens": 600, "completion_tokens": 400},
        )
        return {"candidates": candidates}
    return _call


# ---------- validation ----------


def test_requires_idea_description(db, ai_layer):
    db.table("ideas").insert({
        "idea_id": "idea-empty",
        "user_id": "u1",
        "title": "Empty",
        "description": "   ",
    }).execute()
    with pytest.raises(pd.PartnerDiscoveryError):
        pd.run_discovery(
            db=db, ai_layer=ai_layer,
            user_id="u1", idea_id="idea-empty",
        )


def test_requires_available_ai_layer(db):
    layer = MagicMock()
    layer.is_available.return_value = False
    with pytest.raises(pd.PartnerDiscoveryError):
        pd.run_discovery(db=db, ai_layer=layer, user_id="u1", idea_id="idea-1")


# ---------- happy path ----------


def test_run_discovery_persists_candidates_and_logs_cost(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_candidates_response([
        {
            "name": "Stripe",
            "category": "Payments",
            "website": "stripe.com",
            "integration_type": "api",
            "why_relevant": "Subscription billing",
            "relevance_score": 92,
            "implementation_difficulty": "low",
            "confidence": "high",
        },
        {
            "name": "Bandcamp",
            "category": "Music marketplace",
            "integration_type": "manual",
            "why_relevant": "Existing indie composer audience",
            "relevance_score": 78,
            "confidence": "medium",
        },
    ])

    rows = pd.run_discovery(
        db=db, ai_layer=ai_layer, user_id="u1", idea_id="idea-1",
    )
    assert len(rows) == 2

    # Cost event was logged for the LLM call
    events = db.table("agent_cost_events").select("*").eq("user_id", "u1").execute().data
    assert len(events) == 1
    assert events[0]["agent_kind"] == "partner_discovery"
    assert events[0]["input_tokens"] == 600
    assert events[0]["output_tokens"] == 400

    # agent_run is complete
    runs = db.table("agent_runs").select("*").eq("user_id", "u1").execute().data
    assert len(runs) == 1
    assert runs[0]["status"] == "complete"
    assert runs[0]["agent_kind"] == "partner_discovery"

    # Candidates were persisted
    persisted = db.table("partner_candidates").select("*").eq("idea_id", "idea-1").execute().data
    names = sorted(r["name"] for r in persisted)
    assert names == ["Bandcamp", "Stripe"]


def test_ranking_by_relevance_score(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_candidates_response([
        {"name": "Low", "category": "x", "integration_type": "api", "relevance_score": 30},
        {"name": "High", "category": "x", "integration_type": "api", "relevance_score": 95},
        {"name": "Mid", "category": "x", "integration_type": "api", "relevance_score": 60},
    ])
    rows = pd.run_discovery(db=db, ai_layer=ai_layer, user_id="u1", idea_id="idea-1")
    by_name = {r["name"]: r["rank"] for r in rows}
    assert by_name["High"] == 1
    assert by_name["Mid"] == 2
    assert by_name["Low"] == 3


# ---------- normalization ----------


def test_drops_entries_without_name_or_category(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_candidates_response([
        {"category": "Payments", "integration_type": "api"},                   # missing name
        {"name": "Foo", "integration_type": "api"},                            # missing category
        {"name": "Stripe", "category": "Payments", "integration_type": "api"},  # OK
    ])
    rows = pd.run_discovery(db=db, ai_layer=ai_layer, user_id="u1", idea_id="idea-1")
    assert [r["name"] for r in rows] == ["Stripe"]


def test_clamps_invalid_integration_type_to_unknown(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_candidates_response([
        {"name": "Foo", "category": "x", "integration_type": "telepathy"},
    ])
    rows = pd.run_discovery(db=db, ai_layer=ai_layer, user_id="u1", idea_id="idea-1")
    assert rows[0]["integration_type"] == "unknown"


def test_clamps_relevance_score_into_zero_to_hundred(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_candidates_response([
        {"name": "OverNine", "category": "x", "integration_type": "api", "relevance_score": 9001},
        {"name": "Negative", "category": "x", "integration_type": "api", "relevance_score": -50},
    ])
    rows = pd.run_discovery(db=db, ai_layer=ai_layer, user_id="u1", idea_id="idea-1")
    by_name = {r["name"]: r["relevance_score"] for r in rows}
    assert by_name["OverNine"] == 100
    assert by_name["Negative"] == 0


def test_dedupes_by_lowercased_name(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_candidates_response([
        {"name": "Stripe", "category": "Payments", "integration_type": "api", "relevance_score": 90},
        {"name": "stripe", "category": "Other", "integration_type": "sdk", "relevance_score": 50},
        {"name": "STRIPE", "category": "Yet another", "integration_type": "webhook", "relevance_score": 10},
    ])
    rows = pd.run_discovery(db=db, ai_layer=ai_layer, user_id="u1", idea_id="idea-1")
    assert len(rows) == 1
    # First-seen entry wins (the LLM provides them in rank order)
    assert rows[0]["category"] == "Payments"


# ---------- upsert behavior ----------


def test_rerun_updates_rows_does_not_duplicate(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_candidates_response([
        {"name": "Stripe", "category": "Payments", "integration_type": "api", "relevance_score": 90},
    ])
    pd.run_discovery(db=db, ai_layer=ai_layer, user_id="u1", idea_id="idea-1")

    # Second run with a refined description for Stripe
    ai_layer.generate_structured_response.side_effect = _stub_candidates_response([
        {
            "name": "Stripe",
            "category": "Payments + Tax",
            "integration_type": "api",
            "relevance_score": 95,
            "pricing_notes": "2.9% + 30¢ per transaction",
        },
    ])
    pd.run_discovery(db=db, ai_layer=ai_layer, user_id="u1", idea_id="idea-1")

    persisted = db.table("partner_candidates").select("*").eq("idea_id", "idea-1").execute().data
    assert len(persisted) == 1  # no duplicate
    assert persisted[0]["category"] == "Payments + Tax"  # updated
    assert "Tax" in persisted[0]["category"]


# ---------- approval ----------


def test_approve_candidate_flips_flag_and_stamps_timestamp(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = _stub_candidates_response([
        {"name": "Stripe", "category": "Payments", "integration_type": "api"},
    ])
    rows = pd.run_discovery(db=db, ai_layer=ai_layer, user_id="u1", idea_id="idea-1")
    candidate_id = rows[0]["id"]

    updated = pd.approve_candidate(db=db, user_id="u1", candidate_id=candidate_id, approved=True)
    assert updated["approved"] is True
    assert updated["approved_at"]
    assert updated["approved_by"] == "u1"

    # Reverse the approval
    reversed_row = pd.approve_candidate(db=db, user_id="u1", candidate_id=candidate_id, approved=False)
    assert reversed_row["approved"] is False
    assert reversed_row["approved_at"] is None


def test_approve_missing_candidate_raises(db):
    with pytest.raises(pd.PartnerDiscoveryError):
        pd.approve_candidate(db=db, user_id="u1", candidate_id="nope", approved=True)


# ---------- failure ----------


def test_llm_error_marks_agent_run_failed(db, ai_layer):
    ai_layer.generate_structured_response.side_effect = RuntimeError("LLM crashed")
    with pytest.raises(pd.PartnerDiscoveryError):
        pd.run_discovery(db=db, ai_layer=ai_layer, user_id="u1", idea_id="idea-1")

    runs = db.table("agent_runs").select("*").eq("user_id", "u1").execute().data
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert runs[0]["error_message"]


# ---------- BMC siblings threading ----------


def test_existing_key_partners_section_is_threaded_into_prompt(db, ai_layer):
    # Seed an existing BMC key_partners section.
    db.table("business_model_canvas_sections").insert({
        "id": "bmc-1",
        "idea_id": "idea-1",
        "section_name": "key_partners",
        "content": "Royalty-clearance services (e.g. Songtrust)",
        "content_format": "markdown",
        "needs_user_review": False,
    }).execute()

    captured_messages: list = []

    def _capture(messages, *args, **kwargs):
        captured_messages.extend(messages)
        llm_usage_tap.set_last_usage("gpt-4o-mini", {"prompt_tokens": 100, "completion_tokens": 100})
        return {"candidates": [{"name": "Songtrust", "category": "Royalty clearance", "integration_type": "manual"}]}

    ai_layer.generate_structured_response.side_effect = _capture
    pd.run_discovery(db=db, ai_layer=ai_layer, user_id="u1", idea_id="idea-1")

    user_block = next(m["content"] for m in captured_messages if m["role"] == "user")
    assert "Songtrust" in user_block, "existing key_partners content must appear in the prompt"
