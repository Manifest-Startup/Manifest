import pytest
from unittest.mock import Mock, patch
from app.services.documents.provisional_patent import ProvisionalPatent

@pytest.fixture
def mock_model():
    """Fixture for a mock model with idea and ai_layer."""
    model = Mock()
    model.idea = Mock()
    model.idea.description = "A revolutionary new cat toy."
    model.ai_layer = Mock()
    return model

@pytest.fixture
def patent_service(mock_model):
    """Fixture for the ProvisionalPatent service."""
    return ProvisionalPatent(mock_model)

def test_provisional_patent_initialization(patent_service, mock_model):
    """Test that the ProvisionalPatent service initializes correctly."""
    assert patent_service._model is mock_model
    assert patent_service.summary is None

def test_generate_success(patent_service, mock_model):
    """Test successful generation of a patent draft."""
    mock_model.ai_layer.generate_rich_text.return_value = "This is a patent draft."
    
    result = patent_service.generate()
    
    assert result == "This is a patent draft."
    assert patent_service.summary == "This is a patent draft."
    mock_model.ai_layer.generate_rich_text.assert_called_once()

def test_update_calls_generate(patent_service):
    """Test that the update method calls the generate method."""
    with patch.object(patent_service, 'generate') as mock_generate:
        patent_service.update()
        mock_generate.assert_called_once()

def test_generate_missing_components(patent_service, mock_model):
    """Test that generate raises an AttributeError if a component is missing."""
    # Test without ai_layer
    delattr(mock_model, 'ai_layer')
    with pytest.raises(AttributeError, match="missing Idea or AILayer"):
        patent_service.generate()
        
    # Test without idea
    setattr(patent_service._model, 'ai_layer', Mock()) # Add ai_layer back
    delattr(mock_model, 'idea')
    with pytest.raises(AttributeError, match="missing Idea or AILayer"):
        patent_service.generate()

def test_generate_error_handling(patent_service, mock_model):
    """Test the error handling in the generate method."""
    mock_model.ai_layer.generate_rich_text.side_effect = Exception("AI layer failed")
    
    with pytest.raises(Exception, match="AI layer failed"):
        patent_service.generate() 