from unittest.mock import patch

import pytest
from app.graphql.resolvers import documents
from app.graphql.schema import _start_background_generation


@pytest.fixture(autouse=True)
def _clean_queue():
    documents._pending_generation.clear()
    documents._running_generation.clear()
    yield
    documents._pending_generation.clear()
    documents._running_generation.clear()


def test_start_background_generation_starts_one_thread_with_the_callers_key():
    with patch("app.graphql.resolvers.documents.start_thread_with_current_key") as mock_start:
        result = _start_background_generation("idea-1", "Test idea")

    assert result is True
    # The thread inherits the caller's OpenAI key (BYOK) via start_thread_with_current_key.
    mock_start.assert_called_once_with(documents._drain_generation, "idea-1")
    assert documents._pending_generation == {"idea-1": "Test idea"}


def test_empty_description_starts_nothing():
    with patch("app.graphql.resolvers.documents.start_thread_with_current_key") as mock_start:
        assert _start_background_generation("idea-1", "  ") is False
    mock_start.assert_not_called()


def test_saves_during_a_run_collapse_into_one_run_with_the_newest_text():
    """Autosaves while documents generate must not start parallel runs; the last edit wins."""
    with patch("app.graphql.resolvers.documents.start_thread_with_current_key") as mock_start:
        _start_background_generation("idea-1", "first")
        _start_background_generation("idea-1", "second")
        _start_background_generation("idea-1", "third")
    mock_start.assert_called_once()

    generated = []
    with patch.object(
        documents, "_generate_documents_for_idea", lambda i, d: generated.append((i, d))
    ):
        documents._drain_generation("idea-1")

    assert generated == [("idea-1", "third")]
    assert "idea-1" not in documents._running_generation


def test_an_edit_made_mid_run_gets_its_own_follow_up_run():
    generated = []

    def fake_generate(idea_id, description):
        generated.append(description)
        if description == "first":  # the person keeps typing while this run works
            _start_background_generation(idea_id, "newer")

    with patch("app.graphql.resolvers.documents.start_thread_with_current_key"):
        _start_background_generation("idea-1", "first")
        with patch.object(documents, "_generate_documents_for_idea", fake_generate):
            documents._drain_generation("idea-1")

    assert generated == ["first", "newer"]


def test_a_failed_run_does_not_block_later_edits():
    def boom(idea_id, description):
        raise RuntimeError("model down")

    with patch("app.graphql.resolvers.documents.start_thread_with_current_key"):
        _start_background_generation("idea-1", "text")
        with patch.object(documents, "_generate_documents_for_idea", boom):
            documents._drain_generation("idea-1")
    with patch("app.graphql.resolvers.documents.start_thread_with_current_key") as again:
        _start_background_generation("idea-1", "more")
    again.assert_called_once()
