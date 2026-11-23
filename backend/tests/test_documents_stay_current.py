"""Documents follow the idea: templates never replace written documents, and canvas sections
saved on their own reach the whole canvas the app and the vault show."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.db.database import InMemoryDatabaseClient
from app.services.canvas import orchestrator as bmc
from app.services.documents.demo_documents import build_demo_documents, is_template
from app.services.ideas import document_generation

COLUMNS = (
    "business_model_canvas",
    "similar_ideas",
    "pitch_deck",
    "product_requirements_document",
    "provisional_patent",
)


def test_every_template_is_recognised_and_written_documents_are_not():
    demo = build_demo_documents("Street-level flood sensors that warn neighbours by text.")
    for column in COLUMNS:
        assert is_template(column, getattr(demo, column)), column
        assert not is_template(column, "# Key Partners\n- City water departments"), column
    assert is_template("pitch_deck", None) and is_template("pitch_deck", "  ")


@pytest.fixture
def db():
    client = InMemoryDatabaseClient()
    client.table("ideas").insert(
        {
            "idea_id": "idea-1",
            "user_id": "u1",
            "description": "Flood sensors",
            "business_model_canvas": "# Key Partners\n- City water departments",
            "pitch_deck": build_demo_documents("old text").pitch_deck,
        }
    ).execute()
    with patch.object(document_generation, "create_database_client", return_value=client):
        yield client


def test_only_documents_someone_wrote_are_kept(db):
    kept = document_generation._authored_documents("idea-1", set(COLUMNS))
    assert kept == {"business_model_canvas"}  # the pitch deck is a template; empty ones too


def test_keyless_regeneration_keeps_written_documents_and_refreshes_templates(db):
    saved = {}
    with (
        patch("app.managers.manifest_manager.manifest_manager") as manager,
        patch.object(document_generation, "_get_idea_owner_profile", return_value={"user_id": "u1"}),
        patch.object(
            document_generation, "_update_idea_documents", lambda i, data: saved.update(data)
        ),
        patch.object(document_generation, "_upsert_generated_document"),
    ):
        manager.ai_layer.is_available.return_value = False
        document_generation.generate_background_tasks("Flood sensors for insurers", "idea-1")

    assert "business_model_canvas" not in saved  # written by the person's agent: kept
    assert "Flood sensors for insurers" in saved["pitch_deck"]  # template: refreshed


def test_merge_replaces_one_section_in_place():
    canvas = "# Key Partners\n- a\n# Channels\n- b\n# Cost Structure\n- c"
    merged = bmc.merge_section_into_canvas(canvas, "channels", "- newsletters")
    assert merged.index("# Key Partners") < merged.index("- newsletters") < merged.index("# Cost")
    assert "- b" not in merged and "- a" in merged and "- c" in merged


def test_merge_adds_a_missing_section_and_keeps_heading_level():
    assert bmc.merge_section_into_canvas(None, "channels", "- x") == "# Channels\n- x"
    merged = bmc.merge_section_into_canvas("## Key Partners\n- a", "key_partners", "- p")
    assert merged == "## Key Partners\n- p"
    assert bmc.merge_section_into_canvas("# Key Partners\n- a", "channels", "- x").endswith(
        "# Channels\n- x"
    )


def test_a_saved_section_reaches_the_whole_canvas(db):
    bmc.save_user_section(db=db, idea_id="idea-1", section_name="channels", content="- Local news")
    canvas = db.table("ideas").select("business_model_canvas").eq("idea_id", "idea-1").execute()
    text = canvas.data[0]["business_model_canvas"]
    assert "# Key Partners\n- City water departments" in text and "# Channels\n- Local news" in text


def test_a_template_canvas_keeps_sections_saved_on_their_own(db):
    bmc.save_user_section(db=db, idea_id="idea-1", section_name="channels", content="- Local news")
    canvas = document_generation._with_saved_sections(
        "idea-1", build_demo_documents("Flood sensors").business_model_canvas
    )
    assert "# Channels\n- Local news" in canvas
    assert is_template("business_model_canvas", canvas)  # the rest is still template
