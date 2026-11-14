"""
Tests for integration GraphQL mutations and queries.
"""
import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Mock Supabase response structure
class MockSupabaseResponse:
    def __init__(self, data=None):
        self.data = data or []
        self.count = len(self.data) if self.data else 0

@pytest.fixture
def mock_supabase_client():
    """Create a mock Supabase client."""
    client = Mock()
    return client

@pytest.fixture
def mock_request():
    """Create a mock request with auth token."""
    request = Mock()
    request.headers = {"authorization": "Bearer test_token"}
    return request

@pytest.fixture
def mock_info(mock_supabase_client, mock_request):
    """Create a mock GraphQL info object."""
    info = Mock()
    info.context = {
        "db": mock_supabase_client,
        "supabase": mock_supabase_client,
        "request": mock_request
    }
    return info

@pytest.fixture
def sample_user_id():
    """Sample user ID for testing."""
    return str(uuid.uuid4())

class TestConnectIntegration:
    """Test the connect_integration mutation."""
    
    @pytest.mark.asyncio
    @patch('app.graphql.schema.get_current_user_id')
    async def test_connect_new_integration(self, mock_get_user_id, mock_info, mock_supabase_client, sample_user_id):
        """Test connecting a new integration when none exists."""
        from app.graphql.schema import Mutation, ConnectIntegrationInput
        
        mock_get_user_id.return_value = sample_user_id
        
        # Mock: no existing integration
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MockSupabaseResponse(data=[])
        
        # Mock: successful insert
        new_integration = {
            "integration_id": str(uuid.uuid4()),
            "user_id": sample_user_id,
            "service_id": "google",
            "service_name": "Google",
            "access_token": None,
            "refresh_token": None,
            "expires_at": None,
            "connected_at": datetime.utcnow().isoformat(),
            "metadata": None
        }
        
        insert_mock = Mock()
        insert_mock.execute.return_value = MockSupabaseResponse(data=[new_integration])
        mock_supabase_client.table.return_value.insert.return_value = insert_mock
        
        mutation = Mutation()
        input_data = ConnectIntegrationInput(
            service_id="google",
            access_token=None,
            refresh_token=None,
            expires_at=None,
            metadata=None
        )
        
        result = await mutation.connect_integration(mock_info, input_data)
        
        assert result.service_id == "google"
        assert result.service_name == "Google"
        assert result.user_id == sample_user_id
        
        # Verify insert was called
        mock_supabase_client.table.assert_called_with("integrations")
    
    @pytest.mark.asyncio
    @patch('app.graphql.schema.get_current_user_id')
    async def test_connect_existing_integration(self, mock_get_user_id, mock_info, mock_supabase_client, sample_user_id):
        """Test updating an existing integration."""
        from app.graphql.schema import Mutation, ConnectIntegrationInput
        
        mock_get_user_id.return_value = sample_user_id
        
        # Mock: existing integration found
        existing_integration = {
            "integration_id": str(uuid.uuid4()),
            "user_id": sample_user_id,
            "service_id": "google",
            "service_name": "Google",
            "access_token": "old_token",
            "refresh_token": None,
            "expires_at": None,
            "connected_at": datetime.utcnow().isoformat(),
            "metadata": None
        }
        
        # Mock: existing integration query
        select_mock = Mock()
        select_mock.eq.return_value.eq.return_value.execute.return_value = MockSupabaseResponse(data=[existing_integration])
        mock_supabase_client.table.return_value.select.return_value = select_mock
        
        # Mock: successful update (update().eq().eq().execute())
        updated_integration = {**existing_integration, "access_token": "new_token"}
        update_mock = Mock()
        update_mock.eq.return_value.eq.return_value.execute.return_value = MockSupabaseResponse(data=[updated_integration])
        mock_supabase_client.table.return_value.update.return_value = update_mock
        
        mutation = Mutation()
        input_data = ConnectIntegrationInput(
            service_id="google",
            access_token="new_token",
            refresh_token=None,
            expires_at=None,
            metadata=None
        )
        
        result = await mutation.connect_integration(mock_info, input_data)
        
        assert result.service_id == "google"
        assert result.service_name == "Google"
        
        # Verify update was called
        mock_supabase_client.table.assert_called_with("integrations")

class TestGetIntegrations:
    """Test the integrations query."""
    
    @pytest.mark.asyncio
    @patch('app.graphql.schema.get_current_user_id')
    async def test_get_integrations_empty(self, mock_get_user_id, mock_info, mock_supabase_client, sample_user_id):
        """Test getting integrations when user has none."""
        from app.graphql.schema import Query
        
        mock_get_user_id.return_value = sample_user_id
        
        # Mock: no integrations found
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MockSupabaseResponse(data=[])
        
        query = Query()
        result = await query.integrations(mock_info)
        
        assert result == []
    
    @pytest.mark.asyncio
    @patch('app.graphql.schema.get_current_user_id')
    async def test_get_integrations_with_data(self, mock_get_user_id, mock_info, mock_supabase_client, sample_user_id):
        """Test getting integrations when user has some."""
        from app.graphql.schema import Query
        
        mock_get_user_id.return_value = sample_user_id
        
        # Mock: integrations found
        integrations = [
            {
                "integration_id": str(uuid.uuid4()),
                "user_id": sample_user_id,
                "service_id": "google",
                "service_name": "Google",
                "access_token": "token123",
                "refresh_token": None,
                "expires_at": None,
                "connected_at": datetime.utcnow().isoformat(),
                "metadata": None
            },
            {
                "integration_id": str(uuid.uuid4()),
                "user_id": sample_user_id,
                "service_id": "notion",
                "service_name": "Notion",
                "access_token": "token456",
                "refresh_token": None,
                "expires_at": None,
                "connected_at": datetime.utcnow().isoformat(),
                "metadata": None
            }
        ]
        
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MockSupabaseResponse(data=integrations)
        
        query = Query()
        result = await query.integrations(mock_info)
        
        assert len(result) == 2
        assert result[0].service_id == "google"
        assert result[1].service_id == "notion"
        # Tokens should be masked
        assert result[0].access_token == "***"
        assert result[1].access_token == "***"
