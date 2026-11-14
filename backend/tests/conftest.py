import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-key-minimum-32-characters-long")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRlc3QiLCJyb2xlIjoic2VydmljZV9yb2xlIiwiaWF0IjoxNjQwMDAwMDAwLCJleHAiOjE5NTU1NjAwMDB9.test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-openai-key")
# Task #11 — disable the live HaveIBeenPwned lookup during the test suite so
# (a) tests are hermetic / offline and (b) common test passwords like
# "Password123!" don't trip the breach check. The check itself is exercised
# in tests/test_security_hardening.py with a mocked httpx client.
os.environ.setdefault("DISABLE_HIBP_CHECK", "1")


def create_mock_db_client():
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_response = MagicMock()
    mock_response.data = []
    mock_response.error = None
    
    mock_db.table.return_value = mock_query
    mock_query.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.neq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.single.return_value = mock_query
    mock_query.upsert.return_value = mock_query
    mock_query.insert.return_value = mock_query
    mock_query.update.return_value = mock_query
    mock_query.delete.return_value = mock_query
    mock_query.execute.return_value = mock_response
    
    return mock_db


mock_db = create_mock_db_client()
mock_supabase = mock_db

# Ensure the application reuses the mocked database client instead of requiring
# a real DATABASE_URL during tests.
try:
    from app.db.database import set_db_client_override
    set_db_client_override(mock_supabase)
except Exception:
    pass

_original_create_client = None

def mock_create_client(*args, **kwargs):
    return mock_supabase

try:
    import supabase
    _original_create_client = supabase.create_client
    supabase.create_client = mock_create_client
except ImportError:
    pass

import pytest

@pytest.fixture
def supabase_client():
    """Provide access to the mocked database client (compatible interface)."""
    return mock_db

@pytest.fixture
def db_client():
    """Provide access to the mocked database client."""
    return create_mock_db_client()

@pytest.fixture
def mock_ai_router():
    """Mock AIRouter for AI tests."""
    with patch("app.services.ai.router.AIRouter") as mock:
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock_instance.chat.return_value = "Mock response"
        mock_instance.chat_json.return_value = {"key": "value"}
        mock_instance.embed.return_value = [[0.1, 0.2, 0.3]]
        mock_instance.tts.return_value = b"audio-bytes"
        mock_instance.health_check.return_value = True
        mock.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_openai():
    """Legacy mock for OpenAI (for backward compatibility)."""
    with patch("openai.OpenAI") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture(autouse=True)
def _reset_shared_cache():
    """The process-wide cache (app.services.shared.cache) is keyed state
    shared across tests — clear it so a value cached by one test (e.g. the
    voice agent's conversation context) can never satisfy a lookup in
    another."""
    try:
        from app.services.shared.cache import _reset_for_tests

        _reset_for_tests()
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def _reset_db_override():
    """Guarantee every test uses the shared mock database client."""
    try:
        from app.db.database import set_db_client_override
        global mock_supabase, mock_db
        mock_db = create_mock_db_client()
        mock_supabase = mock_db
        set_db_client_override(mock_supabase)
    except Exception:
        pass
    yield
    try:
        from app.db.database import set_db_client_override
        set_db_client_override(mock_supabase)
    except Exception:
        pass
