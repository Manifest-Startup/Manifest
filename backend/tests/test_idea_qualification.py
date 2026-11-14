"""Tests for the idea-qualification agent service.

Covers the three behaviors that matter:
  - opening turn writes a session row with the seed question
  - LLM-extracted fields merge into nulls only (never overwrite)
  - the agent completes either when the LLM says "complete" or when
    turn_count reaches MAX_TURNS, with a sensible fallback score
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.db.database import InMemoryDatabaseClient
from app.services.ai import idea_qualification as qs


@pytest.fixture
def db():
    return InMemoryDatabaseClient()


@pytest.fixture
def ai_layer():
    layer = MagicMock()
    layer.is_available.return_value = True
    return layer


def test_start_session_seeds_opening_question(db):
    row = qs.start_session(
        db=db,
        user_id="u1",
        initial_idea_text="A marketplace for indie game soundtracks.",
    )
    assert row["status"] == "in_progress"
    assert row["next_question"] == qs.OPENING_QUESTION
    assert row["turn_count"] == 0
    assert len(row["transcript"]) == 1
    assert row["transcript"][0]["role"] == "assistant"


def test_start_session_rejects_empty_idea(db):
    with pytest.raises(qs.QualificationError):
        qs.start_session(db=db, user_id="u1", initial_idea_text="   ")


def test_continue_session_extracts_fields_and_asks_next_question(db, ai_layer):
    session = qs.start_session(db=db, user_id="u1", initial_idea_text="Test idea")
    ai_layer.generate_structured_response.return_value = {
        "extracted_fields": {
            "user_seriousness": 8,
            "user_goals": "Build a sustainable SaaS within 12 months.",
        },
        "decision": "ask_again",
        "next_question": "What does your weekly time budget for this look like?",
    }

    updated = qs.continue_session(
        db=db,
        ai_layer=ai_layer,
        session_id=session["id"],
        user_id="u1",
        user_message="I'm dead serious, this is my full-time focus.",
    )
    assert updated["status"] == "in_progress"
    assert updated["user_seriousness"] == 8
    assert updated["user_goals"].startswith("Build a sustainable")
    assert updated["next_question"].startswith("What does your weekly")
    assert updated["turn_count"] == 1
    # transcript should now have: opening question, user reply, next assistant question
    assert [m["role"] for m in updated["transcript"]] == ["assistant", "user", "assistant"]


def test_extracted_fields_only_fill_nulls(db, ai_layer):
    session = qs.start_session(db=db, user_id="u1", initial_idea_text="Test")
    # First turn: lock in user_seriousness = 9
    ai_layer.generate_structured_response.return_value = {
        "extracted_fields": {"user_seriousness": 9},
        "decision": "ask_again",
        "next_question": "Q?",
    }
    qs.continue_session(
        db=db, ai_layer=ai_layer, session_id=session["id"],
        user_id="u1", user_message="serious",
    )
    # Second turn: agent tries to overwrite to 3 — must be ignored
    ai_layer.generate_structured_response.return_value = {
        "extracted_fields": {"user_seriousness": 3, "user_goals": "Goal text"},
        "decision": "ask_again",
        "next_question": "Q2?",
    }
    after = qs.continue_session(
        db=db, ai_layer=ai_layer, session_id=session["id"],
        user_id="u1", user_message="more",
    )
    assert after["user_seriousness"] == 9, "must not overwrite locked-in value"
    assert after["user_goals"] == "Goal text", "null field must accept new value"


def test_continue_session_completes_with_score(db, ai_layer):
    session = qs.start_session(db=db, user_id="u1", initial_idea_text="Test")
    ai_layer.generate_structured_response.return_value = {
        "extracted_fields": {
            "user_seriousness": 9, "user_domain_knowledge": 8,
            "user_goals": "Ship MVP in 6 months", "user_budget": "$10k",
            "user_timeline": "12 months", "user_execution_ability": 8,
            "idea_market_need": 7, "idea_target_customer": "Indie game devs",
        },
        "decision": "complete",
        "qualification_score": 82,
        "qualification_explanation": "Strong founder, real market.",
    }
    done = qs.continue_session(
        db=db, ai_layer=ai_layer, session_id=session["id"],
        user_id="u1", user_message="Here is everything.",
    )
    assert done["status"] == "complete"
    assert done["qualification_score"] == 82
    assert done["next_question"] is None
    assert "Strong founder" in done["qualification_explanation"]


def test_max_turns_forces_completion_with_fallback_score(db, ai_layer):
    session = qs.start_session(db=db, user_id="u1", initial_idea_text="Test")
    # The LLM keeps saying ask_again, but at turn_count == MAX_TURNS the
    # service must complete with a fallback score derived from filled ints.
    ai_layer.generate_structured_response.return_value = {
        "extracted_fields": {"user_seriousness": 7, "idea_market_need": 6},
        "decision": "ask_again",
        "next_question": "Another?",
    }
    for i in range(qs.MAX_TURNS):
        result = qs.continue_session(
            db=db, ai_layer=ai_layer, session_id=session["id"],
            user_id="u1", user_message=f"reply {i}",
        )
    assert result["status"] == "complete"
    assert result["qualification_score"] is not None
    assert result["qualification_explanation"]


def test_session_belongs_to_other_user_not_visible(db, ai_layer):
    session = qs.start_session(db=db, user_id="u1", initial_idea_text="Test")
    assert qs.get_session(db=db, session_id=session["id"], user_id="someone-else") is None
    with pytest.raises(qs.QualificationError):
        qs.continue_session(
            db=db, ai_layer=ai_layer, session_id=session["id"],
            user_id="someone-else", user_message="hi",
        )


def test_continue_on_completed_session_rejected(db, ai_layer):
    session = qs.start_session(db=db, user_id="u1", initial_idea_text="Test")
    ai_layer.generate_structured_response.return_value = {
        "extracted_fields": {
            "user_seriousness": 9, "user_domain_knowledge": 8,
            "user_goals": "g", "user_budget": "b", "user_timeline": "t",
            "user_execution_ability": 7, "idea_market_need": 7,
            "idea_target_customer": "tc",
        },
        "decision": "complete",
        "qualification_score": 80, "qualification_explanation": "ok",
    }
    qs.continue_session(
        db=db, ai_layer=ai_layer, session_id=session["id"],
        user_id="u1", user_message="finish",
    )
    with pytest.raises(qs.QualificationError):
        qs.continue_session(
            db=db, ai_layer=ai_layer, session_id=session["id"],
            user_id="u1", user_message="more?",
        )


def test_ai_layer_unavailable_does_not_crash(db):
    """If the LLM is offline, the agent should still progress without losing state."""
    session = qs.start_session(db=db, user_id="u1", initial_idea_text="Test")
    layer = MagicMock()
    layer.is_available.return_value = False
    result = qs.continue_session(
        db=db, ai_layer=layer, session_id=session["id"],
        user_id="u1", user_message="hi",
    )
    assert result["status"] == "in_progress"
    assert result["next_question"]  # a fallback question is provided
