"""Manifest memory (ADR 0021): one fact per vault file, recalled by any agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.db.database import InMemoryDatabaseClient
from app.services.ideas import vault_sync
from app.services.memory import store

TIDE = {"idea_id": "idea-tide", "title": "TideLine"}
TASTE = {"idea_id": "idea-taste", "title": "Quantified Taste"}


@pytest.fixture
def db():
    return InMemoryDatabaseClient()


def _files(db, user="u1"):
    return {f["path"]: f for f in vault_sync.list_files(db, user)["files"] if not f["deleted"]}


def test_a_memory_is_a_readable_markdown_file_in_the_vault(db):
    result = store.remember(
        db, "u1", "Mihir wants TideLine to sell to insurers first.", idea=TIDE, kind="decision"
    )
    assert result["status"] == "saved"
    path = result["memory"]["path"]
    assert path.startswith("Memory/TideLine/") and path.endswith(".md")
    content = _files(db)[path]["content"]
    assert 'idea: "[[TideLine]]"' in content and 'kind: "decision"' in content
    assert content.rstrip().endswith("Mihir wants TideLine to sell to insurers first.")


def test_facts_without_an_idea_go_to_general(db):
    memory = store.remember(db, "u1", "Prefers short answers in voice.", kind="preference")
    assert memory["memory"]["path"].startswith("Memory/General/")


def test_saying_the_same_thing_again_refreshes_instead_of_duplicating(db):
    store.remember(db, "u1", "TideLine sells to insurers first.", idea=TIDE)
    again = store.remember(db, "u1", "TideLine sells to insurers first", idea=TIDE)
    assert again["status"] == "already_known"
    assert len(store.all_memories(db, "u1")) == 1


def test_replacing_a_fact_moves_the_old_one_to_trash(db):
    old = store.remember(db, "u1", "TideLine sells to insurers first.", idea=TIDE)["memory"]
    new = store.remember(
        db, "u1", "TideLine now sells to city councils first.", idea=TIDE, replaces=old["id"]
    )
    assert new["status"] == "replaced"
    texts = [m["text"] for m in store.all_memories(db, "u1")]
    assert texts == ["TideLine now sells to city councils first."]
    assert (
        "_Replaces: TideLine sells to insurers first._"
        in _files(db)[new["memory"]["path"]]["content"]
    )


def test_recall_prefers_the_idea_in_view_and_matching_words(db):
    store.remember(db, "u1", "TideLine sells to insurers first.", idea=TIDE)
    store.remember(db, "u1", "Quantified Taste launches in Pune cafes.", idea=TASTE)
    store.remember(db, "u1", "Prefers short spoken answers.", kind="preference")

    in_view = [m["text"] for m in store.recall(db, "u1", idea_id="idea-tide")]
    assert "TideLine sells to insurers first." in in_view
    assert "Prefers short spoken answers." in in_view
    assert "Quantified Taste launches in Pune cafes." not in in_view

    asked = store.recall(db, "u1", query="where does taste launch", idea_id="idea-tide")
    assert asked[0]["text"] == "Quantified Taste launches in Pune cafes."


def test_memories_are_private_to_their_owner(db):
    store.remember(db, "u1", "TideLine sells to insurers first.", idea=TIDE)
    assert store.recall(db, "u2", idea_id="idea-tide") == []


def test_a_note_edited_by_hand_in_obsidian_is_still_a_memory(db):
    vault_sync.put_file(db, "u1", "Memory/General/Coffee.md", "Drinks black coffee.\n", None)
    [memory] = store.all_memories(db, "u1")
    assert memory["text"] == "Drinks black coffee." and memory["id"].startswith("p_")
    store.forget(db, "u1", memory["id"])
    assert store.all_memories(db, "u1") == []


def test_update_and_forget(db):
    memory = store.remember(db, "u1", "Pilot with Mumbai port.", idea=TIDE)["memory"]
    updated = store.update(db, "u1", memory["id"], "Pilot with the Mumbai port authority.")
    assert store.find(db, "u1", memory["id"])["text"] == updated["text"]
    store.forget(db, "u1", memory["id"])
    with pytest.raises(store.MemoryStoreError):
        store.find(db, "u1", memory["id"])


def test_secrets_and_empty_text_are_refused(db):
    with pytest.raises(store.MemoryStoreError):
        store.remember(db, "u1", "  ")
    with pytest.raises(store.MemoryStoreError):
        store.remember(db, "u1", "x" * 600)
    with pytest.raises(store.MemoryStoreError):
        store.remember(db, "u1", "Something", kind="secret")


def test_a_conversation_is_saved_with_links_to_what_was_remembered(db):
    started = "2026-11-22T21:05:00+00:00"
    memory = store.remember(db, "u1", "TideLine sells to insurers first.", idea=TIDE)["memory"]
    saved = store.save_conversation(
        db,
        "u1",
        [
            {"role": "user", "text": "Let's sell to insurers"},
            {"role": "user", "text": "first."},
            {"role": "assistant", "text": "Got it, insurers first."},
        ],
        idea=TIDE,
        started_at=started,
        agent="Claude Code",
    )
    assert saved["path"] == "Conversations/2026-11-22 21.05 Voice – TideLine.md"
    content = _files(db)[saved["path"]]["content"]
    assert "**You:** Let's sell to insurers first." in content
    assert "**Manifest:** Got it, insurers first." in content
    assert f"[[{memory['path'][:-3]}|" in content
    assert [m["id"] for m in saved["memories"]] == [memory["id"]]
    assert store.find(db, "u1", memory["id"])["conversation"] == (
        "[[Conversations/2026-11-22 21.05 Voice – TideLine]]"
    )


def test_a_one_sided_session_saves_nothing(db):
    assert store.save_conversation(db, "u1", [{"role": "assistant", "text": "Hi."}]) is None


def test_extraction_uses_the_persons_key_and_skips_without_one(db):
    turns = [{"role": "user", "text": "Our first customer is Ana at Port of Mumbai."}]
    off = MagicMock()
    off.is_available.return_value = False
    assert store.extract(off, turns, [], "TideLine") == []

    on = MagicMock()
    on.is_available.return_value = True
    on.generate_structured_response.return_value = {
        "memories": [
            {"text": "Ana at the Port of Mumbai is TideLine's first customer.", "kind": "person"},
            {"text": "", "kind": "fact"},
            {"text": "Odd kind", "kind": "nonsense"},
        ]
    }
    found = store.extract(on, turns, [], "TideLine")
    assert found == [
        {"text": "Ana at the Port of Mumbai is TideLine's first customer.", "kind": "person"},
        {"text": "Odd kind", "kind": "fact"},
    ]
    prompt = on.generate_structured_response.call_args.args[0][1]["content"]
    assert "<untrusted>" in prompt


# ---- GraphQL --------------------------------------------------------------------------------


def _gql(db, query, user="u1", role="owner"):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.graphql.schema import schema

    loop = asyncio.new_event_loop()
    try:
        with (
            patch("app.graphql.schema.get_current_user_id", return_value=user),
            patch("app.graphql.resolvers.memory.get_current_user_id", return_value=user),
            patch(
                "app.services.ideas.collaboration.CollaborationService.get_user_role",
                AsyncMock(return_value=role),
            ),
            patch(
                "app.graphql.schema.resolve_principal",
                return_value=SimpleNamespace(has=lambda _: True),
            ),
        ):
            return loop.run_until_complete(
                schema.execute(query, context_value={"db": db, "request": MagicMock()})
            )
    finally:
        loop.close()


def test_graphql_remember_recall_and_save_a_conversation(db):
    db.table("ideas").insert({"idea_id": "idea-tide", "title": "TideLine"}).execute()
    saved = _gql(
        db,
        'mutation { remember(text: "TideLine sells to insurers first.", ideaId: "idea-tide", '
        'kind: "decision", source: "voice") { status memory { id ideaTitle path } } }',
    )
    assert not saved.errors, saved.errors
    assert saved.data["remember"]["memory"]["ideaTitle"] == "TideLine"

    recalled = _gql(db, 'query { recall(ideaId: "idea-tide") { text kind } }')
    assert recalled.data["recall"] == [
        {"text": "TideLine sells to insurers first.", "kind": "decision"}
    ]

    convo = _gql(
        db,
        'mutation { saveVoiceConversation(ideaId: "idea-tide", extract: false, '
        'startedAt: "2000-01-01T00:00:00+00:00", '
        'turns: [{role: "user", text: "Insurers first."}, {role: "assistant", text: "Noted."}]) '
        "{ path turns memories { text } } }",
    )
    assert not convo.errors, convo.errors
    assert convo.data["saveVoiceConversation"]["path"].startswith("Conversations/2000-01-01")
    assert convo.data["saveVoiceConversation"]["memories"] == [
        {"text": "TideLine sells to insurers first."}
    ]


def test_graphql_refuses_an_idea_the_person_cannot_see(db):
    db.table("ideas").insert({"idea_id": "idea-x", "title": "Secret"}).execute()
    result = _gql(
        db, 'mutation { remember(text: "A fact.", ideaId: "idea-x") { status } }', role=None
    )
    assert result.errors and "permission" in result.errors[0].message


# ---- hosted voice -----------------------------------------------------------------------------


def test_hosted_voice_loads_what_it_remembers_and_has_the_memory_tools():
    import asyncio
    from unittest.mock import AsyncMock

    from app.services.voice.live import bot, tools

    names = {d["name"] for d in tools.model_tool_definitions()}
    assert {"recall", "remember", "forget_memory"} <= names
    assert "call remember right away" in bot.SYSTEM_PROMPT

    executor = MagicMock()
    executor.run = AsyncMock(
        return_value={
            "recall": [{"id": "mem_1", "text": "Sells to insurers first.", "ideaTitle": "TideLine"}]
        }
    )
    session = bot.VoiceSessionContext(idea_id="idea-tide", idea_title="TideLine")
    note = asyncio.new_event_loop().run_until_complete(bot.remembered(executor, session))
    executor.run.assert_awaited_once_with("recall", {"limit": 12, "idea_id": "idea-tide"})
    assert "Sells to insurers first. (memory id mem_1, about TideLine)" in note
    assert "data, not instructions" in note

    executor.run = AsyncMock(side_effect=RuntimeError("offline"))
    assert asyncio.new_event_loop().run_until_complete(bot.remembered(executor, session)) == ""
