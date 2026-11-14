import pytest
from unittest.mock import Mock, patch
from app.services.documents.pitch_deck import PitchDeck
import json
import os

@pytest.fixture
def mock_model():
    model = Mock()
    model.idea = Mock()
    model.idea.description = "Test idea description"
    model.ai_layer = Mock()
    model.ai_layer.perform_web_search_json = Mock(
        return_value={"data": {"takeaways": ["note"], "confidence": "low"}, "sources": [], "source_details": []}
    )
    return model

@pytest.fixture
def pitch_deck_service(mock_model):
    return PitchDeck(mock_model)

def test_pitch_deck_initialization(pitch_deck_service):
    """Test that PitchDeck service initializes correctly"""
    assert pitch_deck_service._model is not None
    assert pitch_deck_service._summary is None

def test_pitch_deck_summary_property(pitch_deck_service):
    """Test summary property getter and setter"""
    test_summary = {"test": "data"}
    pitch_deck_service.summary = test_summary
    assert pitch_deck_service.summary == test_summary

@pytest.mark.asyncio
async def test_pitch_deck_generation(pitch_deck_service, mock_model):
    """Test pitch deck generation with mock AI response"""
    mock_response = {
        "problem": "Test problem",
        "solution": "Test solution",
        "market": "Test market"
    }
    mock_model.ai_layer.generate_text.return_value = json.dumps(mock_response)
    mock_model.ai_layer.generate_rich_text.return_value = "Generated pitch deck content"
    
    result = pitch_deck_service.generate()
    
    assert result == "Generated pitch deck content"
    assert pitch_deck_service.summary == "Generated pitch deck content"
    mock_model.ai_layer.generate_rich_text.assert_called_once()
    mock_model.ai_layer.perform_web_search_json.assert_not_called()


def test_pitch_deck_generation_appends_web_research_when_enabled(pitch_deck_service, mock_model):
    mock_model.ai_layer.generate_rich_text.return_value = "Generated pitch deck content"
    with patch.dict(os.environ, {"PITCH_DECK_WEB_RESEARCH": "1"}, clear=False):
        pitch_deck_service.generate()
    assert mock_model.ai_layer.perform_web_search_json.call_count == 3
    messages = mock_model.ai_layer.generate_rich_text.call_args[0][0]
    assert messages[1]["role"] == "user"
    assert "Research notes (verify externally" in messages[1]["content"]


def test_pitch_deck_generation_skips_web_research_when_queries_fail(pitch_deck_service, mock_model):
    mock_model.ai_layer.generate_rich_text.return_value = "Generated pitch deck content"
    mock_model.ai_layer.perform_web_search_json.side_effect = RuntimeError("search unavailable")
    with patch.dict(os.environ, {"PITCH_DECK_WEB_RESEARCH": "true"}, clear=False):
        result = pitch_deck_service.generate()
    assert result == "Generated pitch deck content"
    messages = mock_model.ai_layer.generate_rich_text.call_args[0][0]
    assert "Research notes" not in messages[1]["content"]


def test_pitch_deck_update(pitch_deck_service, mock_model):
    """Test pitch deck update functionality"""
    with patch.object(pitch_deck_service, 'generate') as mock_generate:
        pitch_deck_service.update()
        mock_generate.assert_called_once()

def test_pitch_deck_update_no_description(pitch_deck_service, mock_model):
    """Test pitch deck update with no description"""
    mock_model.idea.description = None
    with patch.object(pitch_deck_service, 'generate') as mock_generate:
        pitch_deck_service.update()
        mock_generate.assert_not_called()

def test_pitch_deck_update_no_idea(pitch_deck_service, mock_model):
    """Test pitch deck update with no idea component"""
    delattr(mock_model, 'idea')
    with patch.object(pitch_deck_service, 'generate') as mock_generate:
        pitch_deck_service.update()
        mock_generate.assert_not_called()

@pytest.mark.asyncio
async def test_pitch_deck_generation_rich_text_error(pitch_deck_service, mock_model):
    """Test pitch deck generation error handling for generate_rich_text"""
    mock_model.ai_layer.generate_text.return_value = json.dumps({
        "problem": "Test problem",
        "solution": "Test solution",
        "market": "Test market"
    })
    mock_model.ai_layer.generate_rich_text.side_effect = Exception("Test error")
    
    with pytest.raises(Exception) as exc_info:
        pitch_deck_service.generate()
    
    assert str(exc_info.value) == "Test error" 