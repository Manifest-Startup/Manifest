"""
Tests for AILayer service using AIRouter backend.
"""

import pytest
from app.services.ai.credentials import MissingOpenAIKeyError
from unittest.mock import patch, Mock, MagicMock
from app.services.ai.layer import AILayer
import os


@pytest.fixture
def mock_router():
    """Fixture for a mock AIRouter."""
    with patch('app.services.ai.layer.AIRouter') as mock:
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock_instance.chat.return_value = "Test response"
        mock_instance.chat_json.return_value = {"key": "value"}
        mock_instance.health_check.return_value = True
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def ai_layer(mock_router):
    """Fixture for the AILayer service."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
        layer = AILayer(max_retries=1)
        layer.router = mock_router
        return layer


def test_ai_layer_initialization():
    """Test AILayer initializes with AIRouter."""
    with patch('app.services.ai.layer.AIRouter') as mock_router:
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock_router.return_value = mock_instance
        
        layer = AILayer()
        assert layer.router is not None


def test_generate_text_success(ai_layer, mock_router):
    """Test successful text generation."""
    mock_router.chat.return_value = "Generated text"
    
    result = ai_layer.generate_text([{"role": "user", "content": "Hello"}])
    
    assert result == "Generated text"
    mock_router.chat.assert_called_once()


def test_generate_text_not_available():
    """Test generate_text when router is not available."""
    with patch('app.services.ai.layer.AIRouter') as mock:
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = False
        mock.return_value = mock_instance
        
        layer = AILayer()
        
        with pytest.raises(Exception, match="not configured"):
            layer.generate_text([{"role": "user", "content": "Hello"}])


def test_generate_text_error(ai_layer, mock_router):
    """Test generate_text handles errors."""
    mock_router.chat.side_effect = Exception("API Error")
    
    with pytest.raises(Exception, match="Failed to generate text"):
        ai_layer.generate_text([{"role": "user", "content": "Hello"}])


def test_generate_rich_text(ai_layer, mock_router):
    """Test rich text generation adds formatting instructions."""
    mock_router.chat.return_value = "# Formatted\n\nText here"
    
    result = ai_layer.generate_rich_text(
        [{"role": "user", "content": "Make this bold"}],
        format_type="markdown"
    )
    
    assert result == "# Formatted\n\nText here"
    
    call_args = mock_router.chat.call_args
    messages = call_args[1]["prompt"]
    assert any("format your response" in str(m.get("content", "")).lower() for m in messages)


def test_generate_rich_text_with_system_message(ai_layer, mock_router):
    """Test rich text adds formatting to existing system message."""
    mock_router.chat.return_value = "Response"
    
    messages = [
        {"role": "system", "content": "Be helpful"},
        {"role": "user", "content": "Hello"}
    ]
    
    ai_layer.generate_rich_text(messages)
    
    call_args = mock_router.chat.call_args
    sent_messages = call_args[1]["prompt"]
    system_msg = sent_messages[0]
    assert "Be helpful" in system_msg["content"]
    assert "format" in system_msg["content"].lower()


def test_generate_summary(ai_layer, mock_router):
    """Test summary generation."""
    mock_router.chat.return_value = "This is a summary."
    
    result = ai_layer.generate_summary("A long idea description about a startup.")
    
    assert result == "This is a summary."
    call_args = mock_router.chat.call_args
    prompt_content = str(call_args[1]["prompt"])
    assert "Summarize" in prompt_content or "summarize" in prompt_content.lower()


def test_health_check_success(ai_layer, mock_router):
    """Test successful health check."""
    mock_router.health_check.return_value = True
    
    result = ai_layer.health_check()
    
    assert result is True


def test_health_check_failure(ai_layer, mock_router):
    """Test failed health check."""
    mock_router.health_check.return_value = False
    
    result = ai_layer.health_check()
    
    assert result is False


def test_health_check_exception(ai_layer, mock_router):
    """Test health check handles exceptions."""
    mock_router.health_check.side_effect = Exception("Network error")
    
    result = ai_layer.health_check()
    
    assert result is False


def test_perform_web_search_success(ai_layer, mock_router):
    """Test successful web search using AIRouter."""
    mock_router.web_search.return_value = {
        "content": "Search result",
        "citations": ["citation1"]
    }
    
    result = ai_layer.perform_web_search("test query")
    
    assert result["similar_ideas"] == "Search result"
    assert "citation1" in result["sources"]
    mock_router.web_search.assert_called_once_with("test query")


def test_perform_web_search_no_router():
    """Test web search when AIRouter is not available."""
    with patch('app.services.ai.layer.AIRouter') as mock_class:
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = False
        mock_class.return_value = mock_instance
        
        layer = AILayer()
        
        with pytest.raises(MissingOpenAIKeyError, match="OpenAI API key"):
            layer.perform_web_search("test query")


def test_perform_web_search_error(ai_layer, mock_router):
    """Test web search handles errors."""
    mock_router.web_search.side_effect = Exception("API Error")
    
    with pytest.raises(Exception, match="Web search failed"):
        ai_layer.perform_web_search("test query")


def test_perform_web_search_json_success(ai_layer, mock_router):
    """Test successful structured web search using AIRouter."""
    mock_router.web_search_json.return_value = {
        "content": {"comparables": [], "research_topics": []},
        "citations": ["https://example.com/report"],
        "citation_details": [{"url": "https://example.com/report", "title": "Example Report"}],
    }

    result = ai_layer.perform_web_search_json("test query", system_prompt="Return JSON")

    assert result["data"] == {"comparables": [], "research_topics": []}
    assert "https://example.com/report" in result["sources"]
    assert result["source_details"][0]["title"] == "Example Report"
    mock_router.web_search_json.assert_called_once_with("test query", system_prompt="Return JSON")


def test_perform_web_search_json_error(ai_layer, mock_router):
    """Test structured web search handles errors."""
    mock_router.web_search_json.side_effect = Exception("API Error")

    with pytest.raises(Exception, match="Structured web search failed"):
        ai_layer.perform_web_search_json("test query")


def test_generate_structured_response_success(ai_layer, mock_router):
    """Test successful structured response generation."""
    mock_router.chat_json.return_value = {"key": "value", "nested": {"data": 123}}
    
    result = ai_layer.generate_structured_response([{"role": "user", "content": "Get JSON"}])
    
    assert result == {"key": "value", "nested": {"data": 123}}


def test_generate_structured_response_error(ai_layer, mock_router):
    """Test structured response handles errors."""
    mock_router.chat_json.side_effect = Exception("JSON parse error")
    
    with pytest.raises(Exception, match="Failed to generate structured response"):
        ai_layer.generate_structured_response([{"role": "user", "content": "Get JSON"}])


def test_model_configuration():
    """Test model configuration from environment."""
    with patch('app.services.ai.layer.AIRouter') as mock:
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock.return_value = mock_instance
        
        with patch.dict(os.environ, {"AI_MODEL": "gpt-4.1-mini"}):
            layer = AILayer()
            assert layer.model == "gpt-4.1-mini"


def test_default_model():
    """Test default model is set."""
    with patch('app.services.ai.layer.AIRouter') as mock:
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock.return_value = mock_instance
        
        layer = AILayer()
        assert layer.DEFAULT_MODEL == "gpt-4o-mini"
