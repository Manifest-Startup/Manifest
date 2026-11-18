"""Agent-authored documents and the Obsidian-style vault (ADR 0005)."""

from __future__ import annotations

import pytest
from app.services.canvas import orchestrator
from app.services.documents import authored
from app.services.ideas import document_generation, vault


# -- document guides and saving ----------------------------------------------------


@pytest.mark.parametrize(
    "name,key",
    [
        ("pitch_deck", "pitch_deck"),
        ("prd", "product_requirements_document"),
        ("Business Model Canvas", "business_model_canvas"),
        ("patent", "provisional_patent"),
        ("competitors", "similar_ideas"),
    ],
)
def test_guides_come_from_manifests_own_prompts(name, key):
    guide = authored.guide(name)
    assert guide["document_type"] == key
    assert guide["system"] and guide["instructions"]
    assert (
        "{{" not in guide["instructions"]
    ), "template placeholders must be explained, not left raw"
    assert "save_idea_document" in guide["save_with"]


def test_pitch_deck_guide_keeps_manifests_slide_structure():
    assert "# Slide 1: Company Purpose" in authored.guide("pitch_deck")["instructions"]


def test_unknown_types_and_bad_content_are_explained():
    with pytest.raises(authored.DocumentError, match="Unknown document type"):
        authored.kind_for("novel")
    with pytest.raises(authored.DocumentError, match="empty"):
        authored.clean_content("   ")
    with pytest.raises(authored.DocumentError, match="longer than"):
        authored.clean_content("x" * (authored.MAX_CHARS + 1))


def test_saved_documents_go_where_generated_ones_go(monkeypatch):
    updates, upserts = [], []
    monkeypatch.setattr(
        document_generation, "_update_idea_documents", lambda i, d: updates.append((i, d))
    )
    monkeypatch.setattr(
        document_generation, "_upsert_generated_document", lambda *a: upserts.append(a)
    )
    kind = authored.save(idea_id="i1", owner_id="u1", document_type="prd", content="  # PRD  ")
    assert kind.key == "product_requirements_document"
    assert updates == [("i1", {"product_requirements_document": "# PRD", "user_id": "u1"})]
    assert upserts == [("product_requirements_documents", "i1", "u1", "# PRD")]
    authored.save(idea_id="i1", owner_id="u1", document_type="similar_ideas", content="x")
    assert len(upserts) == 1, "similar ideas only live on the idea"


class _Upsert:
    def __init__(self):
        self.payload = None

    def table(self, _name):
        return self

    def upsert(self, payload, on_conflict=None):
        self.payload = payload
        return self

    def execute(self):
        return type("R", (), {"data": [self.payload]})()


def test_agent_written_canvas_sections_are_marked_as_user_edits():
    db = _Upsert()
    row = orchestrator.save_user_section(
        db=db, idea_id="i1", section_name="channels", content=" City RFPs "
    )
    assert row["content"] == "City RFPs" and row["last_user_edit_at"]
    assert row["generated_by_run_id"] is None and row["needs_user_review"] is False
    with pytest.raises(orchestrator.BmcSectionError):
        orchestrator.save_user_section(db=db, idea_id="i1", section_name="vibes", content="x")


# -- vault -------------------------------------------------------------------------

IDEAS = [
    {
        "idea_id": "a",
        "title": "TideLine: street flood warnings",
        "description": "Solar water sensors on storm drains text residents before flooding.",
        "created_at": "2026-11-18T03:00:00+00:00",
        "updated_at": "2026-11-18T04:00:00+00:00",
        "is_published": False,
        "required_skills": ["Embedded Systems", "Data Engineering"],
        "pitch_deck": "# Slide 1: Company Purpose\nTideLine.",
        "business_model_canvas": None,
    },
    {
        "idea_id": "b",
        "title": "DrainWatch",
        "description": "Storm drain sensors for cities: flooding alerts and maintenance.",
        "created_at": "2026-11-17T03:00:00+00:00",
        "updated_at": "2026-11-17T03:00:00+00:00",
        "required_skills": ["Embedded Systems"],
    },
]


def _by_path(files):
    return {f["path"]: f["content"] for f in files}


def test_vault_links_ideas_documents_skills_and_related_ideas():
    files = _by_path(
        vault.build_files(
            IDEAS,
            {"a": [{"section_name": "channels", "content": "City RFPs"}]},
            [
                {
                    "id": "s1",
                    "idea_id": "a",
                    "initial_idea_text": "Street-level flood warnings",
                    "transcript": [{"role": "assistant", "content": "Who is it for?"}],
                    "created_at": "2026-11-18T03:57:00+00:00",
                }
            ],
        )
    )
    idea = files["Manifest/Ideas/TideLine street flood warnings.md"]
    assert idea.startswith('---\nmanifest_id: "a"\ntype: "idea"')
    assert vault.BEGIN in idea and vault.END in idea
    assert "[[Manifest/Documents/TideLine street flood warnings/Pitch Deck|Pitch Deck]]" in idea
    assert "[[Manifest/Skills/Embedded Systems|Embedded Systems]]" in idea
    assert "[[Manifest/Ideas/DrainWatch|DrainWatch]]" in idea, "shared skill + words → related"
    assert "skill/embedded-systems" in idea
    canvas = files["Manifest/Documents/TideLine street flood warnings/Business Model Canvas.md"]
    assert (
        "## Channels\nCity RFPs" in canvas
        and "[[Manifest/Ideas/TideLine street flood warnings|" in canvas
    )
    skill = files["Manifest/Skills/Embedded Systems.md"]
    assert "DrainWatch" in skill and "TideLine" in skill
    interview = files["Manifest/Interviews/2026-11-18 Street-level flood warnings.md"]
    assert "**Manifest:** Who is it for?" in interview
    assert "[[Manifest/Ideas/TideLine street flood warnings|" in files["Manifest/Home.md"]


def test_vault_since_skips_unchanged_ideas_but_keeps_hubs():
    files = _by_path(vault.build_files(IDEAS, {}, [], since="2026-11-18T00:00:00+00:00"))
    assert "Manifest/Ideas/TideLine street flood warnings.md" in files
    assert "Manifest/Ideas/DrainWatch.md" not in files
    assert "Manifest/Home.md" in files and "Manifest/Skills/Embedded Systems.md" in files


def test_vault_names_are_file_safe_and_unique():
    twins = [
        {**IDEAS[1], "idea_id": "x1", "title": "Same: name/here?", "created_at": "1"},
        {**IDEAS[1], "idea_id": "x2", "title": "Same: name/here?", "created_at": "2"},
    ]
    paths = {f["path"] for f in vault.build_files(twins, {}, [])}
    assert "Manifest/Ideas/Same name here.md" in paths
    assert "Manifest/Ideas/Same name here (x2).md" in paths
