from unittest.mock import MagicMock, patch

from app.graphql.schema import _generate_documents_for_idea, _start_background_generation


def test_start_background_generation_starts_thread_when_ai_is_unavailable():
    with patch("app.graphql.resolvers.documents.start_thread_with_current_key") as mock_start:
        result = _start_background_generation("idea-1", "Test idea")

    assert result is True
    # The thread inherits the caller's OpenAI key (BYOK) via start_thread_with_current_key.
    mock_start.assert_called_once_with(_generate_documents_for_idea, "idea-1", "Test idea")


def test_start_background_generation_starts_thread_when_ai_is_available():
    with patch("app.graphql.resolvers.documents.start_thread_with_current_key") as mock_start:
        result = _start_background_generation("idea-1", "Test idea")

    assert result is True
    # The thread inherits the caller's OpenAI key (BYOK) via start_thread_with_current_key.
    mock_start.assert_called_once_with(_generate_documents_for_idea, "idea-1", "Test idea")
