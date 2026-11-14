"""
Tests for OAuth routes.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime
import os


class TestOAuthRoutes:
    """Test OAuth route handlers."""
    
    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = Mock()
        request.base_url = "http://localhost:8000/"
        request.headers = {"authorization": "Bearer test_token"}
        request.method = "GET"
        request.query_params = {}
        return request
    
    def test_oauth_providers_config(self):
        """Test that OAuth providers are properly configured."""
        from app.routes.oauth_routes import OAUTH_PROVIDERS
        
        assert "google" in OAUTH_PROVIDERS
        assert "apple" in OAUTH_PROVIDERS
        assert "github" in OAUTH_PROVIDERS
        assert "microsoft" in OAUTH_PROVIDERS
        assert "slack" in OAUTH_PROVIDERS
        assert "notion" in OAUTH_PROVIDERS
        
        for provider, config in OAUTH_PROVIDERS.items():
            assert "auth_url" in config
            assert "token_url" in config
            assert "scopes" in config
            assert "client_id_env" in config
            assert "client_secret_env" in config
    
    def test_get_redirect_uri(self):
        """Test redirect URI generation."""
        from app.routes.oauth_routes import get_redirect_uri
        
        request = Mock()
        request.base_url = "http://localhost:8000/"
        request.headers = {}
        
        uri = get_redirect_uri(request, "google")
        assert "/auth/google/callback" in uri
    
    def test_get_redirect_uri_preserves_scheme(self):
        """Test redirect URI preserves the incoming request scheme."""
        from app.routes.oauth_routes import get_redirect_uri
        
        request = Mock()
        request.base_url = "http://localhost:8000/"
        request.headers = {}
        
        uri = get_redirect_uri(request, "google")
        assert uri.startswith("http://")
    
    @patch.dict(os.environ, {"SUPABASE_JWT_SECRET": "test_signing_key_123"})
    def test_create_and_verify_signed_state(self):
        """Test signed state creation and verification."""
        from app.routes import oauth_routes
        oauth_routes.OAUTH_SIGNING_KEY = "test_signing_key_123"
        oauth_routes._used_nonces.clear()
        from app.routes.oauth_routes import create_signed_state, verify_signed_state
        
        user_id = "user-123"
        provider = "google"
        
        state = create_signed_state(user_id, provider)
        assert "." in state
        
        payload = verify_signed_state(state)
        assert payload is not None
        assert payload["user_id"] == user_id
        assert payload["provider"] == provider
    
    @patch.dict(os.environ, {"SUPABASE_JWT_SECRET": "test_signing_key_123"})
    def test_verify_signed_state_invalid(self):
        """Test that invalid signed state is rejected."""
        from app.routes import oauth_routes
        oauth_routes.OAUTH_SIGNING_KEY = "test_signing_key_123"
        from app.routes.oauth_routes import verify_signed_state
        
        result = verify_signed_state("invalid.state")
        assert result is None
        
        result = verify_signed_state("no_dot_in_state")
        assert result is None
    
    @patch.dict(os.environ, {"SUPABASE_JWT_SECRET": "test_signing_key_123"})
    def test_verify_signed_state_replay_protection(self):
        """Test that signed state cannot be replayed."""
        from app.routes import oauth_routes
        oauth_routes.OAUTH_SIGNING_KEY = "test_signing_key_123"
        oauth_routes._used_nonces.clear()
        from app.routes.oauth_routes import create_signed_state, verify_signed_state
        
        state = create_signed_state("user-123", "google")
        
        payload1 = verify_signed_state(state)
        assert payload1 is not None
        
        payload2 = verify_signed_state(state)
        assert payload2 is None
    
    @pytest.mark.asyncio
    @patch('app.routes.oauth_routes.get_user_id_from_request')
    async def test_oauth_start_unsupported_provider(self, mock_get_user_id):
        """Test OAuth start with unsupported provider."""
        from app.routes.oauth_routes import oauth_start
        from fastapi import HTTPException
        
        mock_get_user_id.return_value = "user-123"
        
        request = Mock()
        request.base_url = "http://localhost:8000/"
        
        with pytest.raises(HTTPException) as exc_info:
            await oauth_start(request, "unsupported_provider")
        
        assert exc_info.value.status_code == 400
        assert "Unsupported provider" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    @patch('app.routes.oauth_routes.get_user_id_from_request')
    async def test_oauth_start_not_configured(self, mock_get_user_id):
        """Test OAuth start when provider is not configured."""
        from app.routes.oauth_routes import oauth_start
        
        mock_get_user_id.return_value = "user-123"
        
        request = Mock()
        request.base_url = "http://localhost:8000/"
        
        with patch.dict(os.environ, {}, clear=True):
            result = await oauth_start(request, "google")
        
        assert result["error"] == "not_configured"
        assert result["provider"] == "google"
    
    @pytest.mark.asyncio
    @patch('app.routes.oauth_routes.get_user_id_from_request')
    @patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "test_client_id", "SUPABASE_JWT_SECRET": "test_key"})
    async def test_oauth_start_success(self, mock_get_user_id):
        """Test successful OAuth start."""
        from app.routes import oauth_routes
        oauth_routes.OAUTH_SIGNING_KEY = "test_key"
        oauth_routes._used_nonces.clear()
        from app.routes.oauth_routes import oauth_start, verify_signed_state
        
        mock_get_user_id.return_value = "user-123"
        
        request = Mock()
        request.base_url = "http://localhost:8000/"
        
        result = await oauth_start(request, "google")
        
        assert "auth_url" in result
        assert result["provider"] == "google"
        assert "state" in result
        payload = verify_signed_state(result["state"])
        assert payload is not None
        assert payload["user_id"] == "user-123"
        assert payload["provider"] == "google"
    
    @pytest.mark.asyncio
    @patch('app.routes.oauth_routes.get_user_id_from_request')
    async def test_oauth_start_requires_auth(self, mock_get_user_id):
        """Test OAuth start requires authentication."""
        from app.routes.oauth_routes import oauth_start
        from fastapi import HTTPException
        
        mock_get_user_id.return_value = None
        
        request = Mock()
        request.base_url = "http://localhost:8000/"
        
        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "test_id"}):
            with pytest.raises(HTTPException) as exc_info:
                await oauth_start(request, "google")
            
            assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_oauth_callback_unsupported_provider(self):
        """Test OAuth callback with unsupported provider."""
        from app.routes.oauth_routes import oauth_callback
        from fastapi import HTTPException
        
        request = Mock()
        request.method = "GET"
        request.query_params = {}
        
        with pytest.raises(HTTPException) as exc_info:
            await oauth_callback(request, "unsupported_provider")
        
        assert exc_info.value.status_code == 400
    
    @pytest.mark.asyncio
    async def test_oauth_callback_with_error(self):
        """Test OAuth callback when provider returns error."""
        from app.routes.oauth_routes import oauth_callback
        
        request = Mock()
        request.method = "GET"
        request.query_params = {"error": "access_denied"}
        
        result = await oauth_callback(request, "google")
        
        assert "Connection Failed" in result.body.decode()
    
    @pytest.mark.asyncio
    async def test_oauth_callback_invalid_state(self):
        """Test OAuth callback with invalid state."""
        from app.routes.oauth_routes import oauth_callback
        
        request = Mock()
        request.method = "GET"
        request.query_params = {"code": "test_code", "state": "invalid_state"}
        
        result = await oauth_callback(request, "google")
        
        assert "Invalid or expired session" in result.body.decode()
    
    @pytest.mark.asyncio
    async def test_oauth_status_supported_provider(self):
        """Test OAuth status for supported provider."""
        from app.routes.oauth_routes import oauth_status
        
        request = Mock()
        
        result = await oauth_status(request, "google")
        
        assert result["provider"] == "google"
        assert "configured" in result
    
    @pytest.mark.asyncio
    async def test_oauth_status_unsupported_provider(self):
        """Test OAuth status for unsupported provider."""
        from app.routes.oauth_routes import oauth_status
        
        request = Mock()
        
        result = await oauth_status(request, "unsupported")
        
        assert result["configured"] is False
        assert result["provider"] == "unsupported"
    
    def test_render_callback_page_success(self):
        """Test callback page rendering on success."""
        from app.routes.oauth_routes import _render_callback_page
        
        result = _render_callback_page(success=True, provider="google")
        
        assert "Connected!" in result.body.decode()
        assert "google" in result.body.decode()
    
    def test_render_callback_page_error(self):
        """Test callback page rendering on error."""
        from app.routes.oauth_routes import _render_callback_page
        
        result = _render_callback_page(success=False, provider="google", error="Test error")
        
        assert "Connection Failed" in result.body.decode()
        assert "Test error" in result.body.decode()


class TestOAuthIntegrationWithDB:
    """Test OAuth routes with database interactions."""
    
    @pytest.fixture
    def mock_supabase(self):
        """Create a mock Supabase client."""
        client = Mock()
        return client
    
    @pytest.mark.asyncio
    @patch("app.routes.oauth_routes.save_integration", return_value=True)
    @patch.dict(os.environ, {
        "GOOGLE_CLIENT_ID": "test_client_id",
        "GOOGLE_CLIENT_SECRET": "test_client_secret",
        "SUPABASE_JWT_SECRET": "test_secret"
    })
    async def test_oauth_callback_stores_integration(self, mock_save_integration):
        """Test that OAuth callback stores integration in database."""
        from app.routes import oauth_routes
        oauth_routes.OAUTH_SIGNING_KEY = "test_secret"
        oauth_routes._used_nonces.clear()
        from app.routes.oauth_routes import oauth_callback, create_signed_state
        import httpx
        
        test_state = create_signed_state("user-123", "google")
        
        request = Mock()
        request.method = "GET"
        request.base_url = "http://localhost:8000/"
        request.query_params = {"code": "test_code", "state": test_state}
        
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600
            }
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=Mock(
                post=AsyncMock(return_value=mock_response)
            ))
            mock_httpx.return_value.__aexit__ = AsyncMock()
            
            result = await oauth_callback(request, "google")
        
        assert "Connected!" in result.body.decode()
        mock_save_integration.assert_called_once()
