"""Each idea's knowledge graph: passages, concepts, citations, vault notes (ADR 0006)."""

from __future__ import annotations

import re

from app.services.ideas import knowledge_graph as kg
from app.services.ideas import vault

NOTE = (
    "Coastal neighborhoods flood street by street, but public warnings cover whole counties. "
    "TideLine puts solar water-level sensors on storm drains and seawalls. "
    "Cities and insurers pay a per-sensor subscription; residents get flood alerts free."
)
DECK = """# Slide 1: Company Purpose
TideLine warns coastal residents before floodwater reaches their street from storm drains.
- Solar sensors on storm drains and seawalls measure rising water.

# Slide 2: Business Model
Cities and insurers pay a per-sensor subscription for flood alerts.

| Plan | Price |
|---|---|
| City | $40 per sensor |

```json
{"sensors": "storm drains"}
```
"""
TARGET = "Manifest/Ideas/TideLine"


def _idea(**extra):
    return {"idea_id": "i1", "title": "TideLine", "description": NOTE, **extra}


def test_note_and_answers_become_citable_passages():
    passages = kg.source_passages(NOTE, ["Insurers asked us for block-level flood data."])
    assert [p["id"] for p in passages] == ["p1", "p2", "p3", "a1"]
    assert passages[1]["text"].startswith("TideLine puts solar")
    assert passages[-1]["kind"] == "answer"


def test_interview_answers_are_the_founders_words_only():
    sessions = [
        {
            "created_at": "2026-11-17",
            "initial_idea_text": "Flood alerts",
            "transcript": '[{"role": "assistant", "content": "Who pays?"},'
            ' {"role": "user", "content": "Insurers and cities pay."}]',
        }
    ]
    assert kg.interview_answers(sessions) == ["Flood alerts", "Insurers and cities pay."]


def test_concepts_come_from_repeated_phrases_and_skills():
    concepts = kg.extract_concepts(NOTE + "\n" + NOTE, DECK, ["Embedded Systems"])
    assert concepts[0] == "Embedded Systems"
    keys = {kg.key(c) for c in concepts}
    assert "sensor" in keys and "storm drain" in keys
    assert not any(kg.key(c) in {"the", "and", "public"} for c in concepts)


def test_every_substantial_line_cites_the_idea_note():
    concepts = ["flood", "sensor", "storm drain", "insurer"]
    cited = kg.cite_document(DECK, TARGET, kg.source_passages(NOTE, []), concepts)
    lines = cited.split("\n")
    assert lines[0] == "# Slide 1: Company Purpose", "headings are never rewritten"
    assert re.search(r"\[\[Manifest/Ideas/TideLine#\^p\d\|↩\]\]$", lines[1])
    assert (
        "[[Manifest/Ideas/TideLine#^p3|↩]]" in cited
    ), "the pricing line cites the pricing sentence"
    assert "| City | $40 per sensor |" in cited, "tables stay intact"
    assert '{"sensors": "storm drains"}' in cited, "code fences stay intact"
    assert "[[Manifest/Concepts/Sensor|sensors]]" in cited
    # Removing the generated links gives back the stored document (what the app checks).
    stripped = re.sub(r" \[\[[^\]]*\|↩\]\]", "", cited)
    stripped = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", stripped)
    assert stripped == DECK


def test_a_document_with_nothing_to_cite_still_links_the_note():
    assert kg.cite_document("Short.", TARGET, [], []).endswith(
        f"Source: [[{TARGET}|original idea note]]"
    )


def test_graph_links_concepts_across_the_persons_ideas():
    other = {"idea_id": "i2", "title": "Sensor Rent", "description": "Rent sensors to insurers."}
    graph = kg.build_graph(
        _idea(),
        {"pitch_deck": DECK},
        [],
        [_idea(), other],
        idea_target=TARGET,
        idea_targets={"i1": TARGET, "i2": "Manifest/Ideas/Sensor Rent"},
    )
    sensor = next(c for c in graph["concepts"] if kg.key(c["label"]) == "sensor")
    assert sensor["ideas"] == ["i2"] and "pitch_deck" in sensor["documents"]
    assert graph["related"][0]["idea_id"] == "i2"
    assert f"[[{TARGET}#^" in graph["documents"]["pitch_deck"]


def test_vault_has_block_ids_concept_hubs_and_cited_documents():
    ideas = [
        _idea(created_at="2026-11-01", pitch_deck=DECK),
        {
            "idea_id": "i2",
            "title": "Sensor Rent",
            "description": "Rent flood sensors to insurers on storm drains.",
            "created_at": "2026-11-02",
        },
    ]
    files = {f["path"]: f["content"] for f in vault.build_files(ideas, {}, [])}
    note = files["Manifest/Ideas/TideLine.md"]
    assert "TideLine puts solar water-level sensors on storm drains and seawalls. ^p2" in note
    assert "## Concepts" in note and "[[Manifest/Concepts/" in note
    assert "[[Manifest/Ideas/Sensor Rent|Sensor Rent]] — shares" in note
    deck = files["Manifest/Documents/TideLine/Pitch Deck.md"]
    assert "[[Manifest/Ideas/TideLine#^p" in deck
    hub = files["Manifest/Concepts/Sensor.md"]
    assert "[[Manifest/Ideas/TideLine|TideLine]]" in hub and "Sensor Rent" in hub
    assert "[[Manifest/Ideas/TideLine#^p2|^p2]]" in hub
    assert "## Concepts" in files["Manifest/Home.md"]


class _FakeDb:
    """Just enough of the Supabase-style table API for idea_knowledge_graph."""

    def __init__(self, tables):
        self.tables, self.rows = tables, []

    def table(self, name):
        self.rows = list(self.tables.get(name, []))
        return self

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.rows = [r for r in self.rows if str(r.get(column)) == str(value)]
        return self

    def order(self, *_, **__):
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def execute(self):
        return type("R", (), {"data": self.rows})()


def test_api_graph_is_owner_only_and_cites_interview_answers():
    db = _FakeDb(
        {
            "ideas": [
                {**_idea(pitch_deck=DECK), "user_id": "u1"},
                {
                    "idea_id": "i2",
                    "title": "Sensor Rent",
                    "description": "Sensors.",
                    "user_id": "u1",
                },
            ],
            "idea_qualification_sessions": [
                {
                    "idea_id": "i1",
                    "user_id": "u1",
                    "transcript": [{"role": "user", "content": "Insurers pay per sensor today."}],
                }
            ],
        }
    )
    assert vault.idea_knowledge_graph(db, "someone-else", "i1") is None
    graph = vault.idea_knowledge_graph(db, "u1", "i1")
    assert graph["idea_target"] == "Manifest/Ideas/TideLine"
    assert graph["passages"][-1] == {
        "id": "a1",
        "kind": "answer",
        "text": "Insurers pay per sensor today.",
    }
    assert graph["titles"]["i2"] == "Sensor Rent"
    assert "[[Manifest/Ideas/TideLine#^" in graph["documents"]["pitch_deck"]


def test_incremental_sync_includes_ideas_with_new_interview_answers():
    ideas = [_idea(created_at="2026-11-01", updated_at="2026-11-01")]
    interviews = [
        {
            "id": "s1",
            "idea_id": "i1",
            "created_at": "2026-11-01",
            "updated_at": "2026-11-17",
            "transcript": [{"role": "user", "content": "Insurers already pay for flood data."}],
        }
    ]
    files = {
        f["path"]: f["content"]
        for f in vault.build_files(ideas, {}, interviews, since="2026-11-10")
    }
    assert "Insurers already pay for flood data. ^a1" in files["Manifest/Ideas/TideLine.md"]
