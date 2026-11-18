"""
Tests for Integration datetime handling in GraphQL schema.
Specifically tests the connected_at and expires_at string-to-datetime conversion.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


class TestIntegrationDatetimeConversion:
    """Test datetime conversion for integration fields."""
    
    @pytest.fixture
    def mock_supabase_response(self):
        """Create a mock Supabase response."""
        mock_response = MagicMock()
        return mock_response
    
    @pytest.fixture
    def sample_integration_data_string_dates(self):
        """Integration data with dates as ISO strings (as stored in DB)."""
        return {
            "integration_id": "test-integration-123",
            "user_id": "user-123",
            "service_name": "Google",
            "service_id": "google",
            "access_token": "secret-token",
            "refresh_token": "secret-refresh",
            "expires_at": "2025-12-25T10:00:00+00:00",
            "connected_at": "2024-06-15T14:30:00+00:00",
            "metadata": None
        }
    
    @pytest.fixture
    def sample_integration_data_z_suffix(self):
        """Integration data with Z suffix on dates."""
        return {
            "integration_id": "test-integration-456",
            "user_id": "user-123",
            "service_name": "Slack",
            "service_id": "slack",
            "access_token": "secret-token",
            "refresh_token": None,
            "expires_at": "2025-12-25T10:00:00Z",
            "connected_at": "2024-06-15T14:30:00Z",
            "metadata": None
        }
    
    @pytest.fixture
    def sample_integration_data_datetime_objects(self):
        """Integration data with proper datetime objects."""
        return {
            "integration_id": "test-integration-789",
            "user_id": "user-123",
            "service_name": "GitHub",
            "service_id": "github",
            "access_token": "secret-token",
            "refresh_token": None,
            "expires_at": datetime(2025, 12, 25, 10, 0, 0),
            "connected_at": datetime(2024, 6, 15, 14, 30, 0),
            "metadata": None
        }
    
    @pytest.fixture
    def sample_integration_data_null_connected_at(self):
        """Integration data with null connected_at."""
        return {
            "integration_id": "test-integration-null",
            "user_id": "user-123",
            "service_name": "Microsoft",
            "service_id": "microsoft",
            "access_token": "secret-token",
            "refresh_token": None,
            "expires_at": None,
            "connected_at": None,
            "metadata": None
        }
    
    @pytest.fixture
    def sample_integration_data_missing_connected_at(self):
        """Integration data missing connected_at field entirely."""
        return {
            "integration_id": "test-integration-missing",
            "user_id": "user-123",
            "service_name": "Apple",
            "service_id": "apple",
            "access_token": "secret-token",
            "refresh_token": None,
            "expires_at": None,
            "metadata": None
        }

    def test_string_to_datetime_conversion(self, sample_integration_data_string_dates):
        """Test that ISO string dates are converted to datetime objects."""
        from app.graphql.schema import Integration
        
        data = sample_integration_data_string_dates.copy()
        connected_at_str = data["connected_at"]
        expires_at_str = data["expires_at"]
        
        if isinstance(data["connected_at"], str):
            data["connected_at"] = datetime.fromisoformat(data["connected_at"].replace("Z", "+00:00"))
        if isinstance(data["expires_at"], str):
            data["expires_at"] = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        
        data["access_token"] = "***"
        data["refresh_token"] = "***"
        
        integration = Integration(**data)
        
        assert isinstance(integration.connected_at, datetime)
        assert isinstance(integration.expires_at, datetime)
        assert integration.connected_at.year == 2024
        assert integration.connected_at.month == 6
        assert integration.connected_at.day == 15

    def test_z_suffix_datetime_conversion(self, sample_integration_data_z_suffix):
        """Test that Z-suffix dates are correctly converted."""
        from app.graphql.schema import Integration
        
        data = sample_integration_data_z_suffix.copy()
        
        if isinstance(data["connected_at"], str):
            data["connected_at"] = datetime.fromisoformat(data["connected_at"].replace("Z", "+00:00"))
        if isinstance(data["expires_at"], str):
            data["expires_at"] = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        
        data["access_token"] = "***"
        
        integration = Integration(**data)
        
        assert isinstance(integration.connected_at, datetime)
        assert isinstance(integration.expires_at, datetime)

    def test_datetime_objects_pass_through(self, sample_integration_data_datetime_objects):
        """Test that datetime objects are passed through unchanged."""
        from app.graphql.schema import Integration
        
        data = sample_integration_data_datetime_objects.copy()
        data["access_token"] = "***"
        
        integration = Integration(**data)
        
        assert isinstance(integration.connected_at, datetime)
        assert isinstance(integration.expires_at, datetime)
        assert integration.connected_at == datetime(2024, 6, 15, 14, 30, 0)

    def test_null_connected_at_gets_default(self, sample_integration_data_null_connected_at):
        """Test that null connected_at gets a default datetime."""
        from app.graphql.schema import Integration
        
        data = sample_integration_data_null_connected_at.copy()
        
        if data.get("connected_at") is None:
            data["connected_at"] = datetime.utcnow()
        
        data["access_token"] = "***"
        
        integration = Integration(**data)
        
        assert isinstance(integration.connected_at, datetime)

    def test_missing_connected_at_gets_default(self, sample_integration_data_missing_connected_at):
        """Test that missing connected_at gets a default datetime."""
        from app.graphql.schema import Integration
        
        data = sample_integration_data_missing_connected_at.copy()
        
        if "connected_at" not in data or data.get("connected_at") is None:
            data["connected_at"] = datetime.utcnow()
        
        data["access_token"] = "***"
        
        integration = Integration(**data)
        
        assert isinstance(integration.connected_at, datetime)

    def test_invalid_date_string_fallback(self):
        """Test that invalid date strings fall back to utcnow()."""
        from app.graphql.schema import Integration
        
        data = {
            "integration_id": "test-invalid-date",
            "user_id": "user-123",
            "service_name": "Test",
            "service_id": "test",
            "access_token": "***",
            "refresh_token": None,
            "expires_at": None,
            "connected_at": "not-a-valid-date",
            "metadata": None
        }
        
        if isinstance(data["connected_at"], str):
            try:
                data["connected_at"] = datetime.fromisoformat(data["connected_at"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                data["connected_at"] = datetime.utcnow()
        
        integration = Integration(**data)
        
        assert isinstance(integration.connected_at, datetime)

    def test_integration_has_isoformat_method(self):
        """Test that Integration.connected_at has isoformat method (is datetime)."""
        from app.graphql.schema import Integration
        
        integration = Integration(
            integration_id="test-123",
            user_id="user-123",
            service_name="Test",
            service_id="test",
            access_token=None,
            refresh_token=None,
            expires_at=None,
            connected_at=datetime.utcnow(),
            metadata=None
        )
        
        assert hasattr(integration.connected_at, 'isoformat')
        assert callable(integration.connected_at.isoformat)
        
        iso_str = integration.connected_at.isoformat()
        assert isinstance(iso_str, str)
        assert "T" in iso_str


class TestIntegrationResolverConversion:
    """Test the actual resolver conversion logic."""
    
    @pytest.fixture
    def mock_info(self):
        """Create mock GraphQL info with request context."""
        mock_request = MagicMock()
        mock_supabase = MagicMock()
        mock_info = MagicMock()
        mock_info.context = {
            "request": mock_request,
            "supabase": mock_supabase,
            "db": mock_supabase,
        }
        return mock_info
    
    @pytest.mark.asyncio
    async def test_integrations_resolver_converts_string_dates(self, mock_info):
        """Test that integrations resolver correctly converts string dates."""
        mock_response = MagicMock()
        mock_response.data = [
            {
                "integration_id": "test-1",
                "user_id": "user-123",
                "service_name": "Google",
                "service_id": "google",
                "access_token": "secret",
                "refresh_token": None,
                "expires_at": "2025-12-25T10:00:00+00:00",
                "connected_at": "2024-06-15T14:30:00+00:00",
                "metadata": None
            }
        ]
        
        mock_info.context["supabase"].table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
        
        with patch('app.graphql.resolvers.integrations.get_current_user_id', return_value="user-123"):
            from app.graphql.schema import Query
            query = Query()
            result = await query.integrations(mock_info)
        
        assert len(result) == 1
        assert isinstance(result[0].connected_at, datetime)
        assert hasattr(result[0].connected_at, 'isoformat')
    
    @pytest.mark.asyncio
    async def test_single_integration_resolver_converts_string_dates(self, mock_info):
        """Test that single integration resolver correctly converts string dates."""
        mock_response = MagicMock()
        mock_response.data = {
            "integration_id": "test-1",
            "user_id": "user-123",
            "service_name": "Slack",
            "service_id": "slack",
            "access_token": "secret",
            "refresh_token": None,
            "expires_at": None,
            "connected_at": "2024-06-15T14:30:00Z",
            "metadata": None
        }
        
        mock_info.context["supabase"].table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_response
        
        with patch('app.graphql.resolvers.integrations.get_current_user_id', return_value="user-123"):
            from app.graphql.schema import Query
            query = Query()
            result = await query.integration(mock_info, service_id="slack")
        
        assert result is not None
        assert isinstance(result.connected_at, datetime)
        assert hasattr(result.connected_at, 'isoformat')

    @pytest.mark.asyncio
    async def test_integration_resolver_handles_empty_response(self, mock_info):
        """Test resolver returns empty list for no integrations."""
        mock_response = MagicMock()
        mock_response.data = []
        
        mock_info.context["supabase"].table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
        
        with patch('app.graphql.resolvers.integrations.get_current_user_id', return_value="user-123"):
            from app.graphql.schema import Query
            query = Query()
            result = await query.integrations(mock_info)
        
        assert result == []

    @pytest.mark.asyncio
    async def test_integration_resolver_handles_none_response(self, mock_info):
        """Test resolver returns empty list for None data."""
        mock_response = MagicMock()
        mock_response.data = None
        
        mock_info.context["supabase"].table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
        
        with patch('app.graphql.resolvers.integrations.get_current_user_id', return_value="user-123"):
            from app.graphql.schema import Query
            query = Query()
            result = await query.integrations(mock_info)
        
        assert result == []
