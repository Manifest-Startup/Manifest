"""Request-level guards for lightweight idea reads, including fragments."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.graphql.schema import schema


def run_query(query, context):
    # Do not replace/clear the process event loop used by neighboring tests.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(schema.execute(query, context_value=context))
    finally:
        loop.close()


def run_idea(query):
    db = MagicMock()
    builder = db.table.return_value
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.single.return_value = builder
    builder.execute.return_value.data = {
        "idea_id": "synthetic-idea",
        "user_id": "synthetic-user",
        "title": "Synthetic note",
        "description": "Saved words",
        "created_at": "2026-01-01T00:00:00+00:00",
        "is_published": False,
        "pitch_deck": "Synthetic deck",
        "similar_ideas": "Related ideas",
    }
    with (
        patch("app.graphql.schema.get_current_user_id", return_value="synthetic-user"),
        patch("app.graphql.resolvers.ideas.get_current_user_id", return_value="synthetic-user"),
        patch(
            "app.graphql.schema.resolve_principal", return_value=SimpleNamespace(has=lambda _: True)
        ),
    ):
        result = run_query(query, {"db": db, "request": MagicMock()})
    return result, builder


def test_note_read_excludes_document_blobs_and_keeps_owner_filter():
    result, builder = run_idea("""query { idea(ideaId: "synthetic-idea") {
        ideaId title description
    } }""")
    assert not result.errors
    assert result.data["idea"]["description"] == "Saved words"
    columns = builder.select.call_args.args[0].split(", ")
    assert "description" in columns
    assert not set(columns) & {
        "pitch_deck",
        "business_model_canvas",
        "provisional_patent",
        "product_requirements_document",
        "similar_ideas",
    }
    builder.eq.assert_any_call("user_id", "synthetic-user")
    builder.eq.assert_any_call("idea_id", "synthetic-idea")
    builder.execute.assert_called_once()


def test_fragments_and_aliases_select_only_requested_documents():
    result, builder = run_idea("""query { note: idea(ideaId: "synthetic-idea") {
        ...DocumentFields
        ... on Idea { related: similarIdeas }
    } }
    fragment DocumentFields on Idea { deck: pitchDeck }
    """)
    assert not result.errors
    assert result.data["note"] == {"deck": "Synthetic deck", "related": "Related ideas"}
    columns = builder.select.call_args.args[0].split(", ")
    assert "pitch_deck" in columns and "similar_ideas" in columns
    assert "description" not in columns
    assert "provisional_patent" not in columns


def test_unauthenticated_idea_read_does_not_access_database():
    db = MagicMock()
    with patch("app.graphql.schema.get_current_user_id", return_value=None):
        result = run_query(
            '{ idea(ideaId: "private") { title } }', {"db": db, "request": MagicMock()}
        )
    assert result.errors
    db.table.assert_not_called()
