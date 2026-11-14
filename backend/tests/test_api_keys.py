"""
Tests for API Key Service and API v1 Routes

Covers:
- API key generation and validation
- API client management
- Usage tracking
- Rate limiting
- REST API endpoints parity with GraphQL
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import hashlib


class TestApiKeyGeneration:
    """Tests for API key generation and hashing."""
    
    def test_generate_api_key_format(self):
        """Test that generated API keys have the correct format."""
        from app.services.identity.api_keys import generate_api_key, API_KEY_PREFIX

        # Post Task #11 ``generate_api_key`` returns a 4-tuple; the new
        # ``hash_algo`` is either "bcrypt" (preferred) or "sha256" (legacy
        # fallback when bcrypt is unavailable).
        full_key, key_prefix, key_hash, hash_algo = generate_api_key()

        assert full_key.startswith(API_KEY_PREFIX)
        assert len(full_key) >= 32
        assert key_prefix == full_key[:16]
        assert hash_algo in ("bcrypt", "sha256")
        # bcrypt hashes start with $2 and are ~60 chars; sha256 hex is 64 chars.
        assert len(key_hash) >= 60

    def test_generate_api_key_unique(self):
        """Test that each generated key is unique."""
        from app.services.identity.api_keys import generate_api_key

        keys = set()
        for _ in range(10):
            full_key, *_ = generate_api_key()
            keys.add(full_key)

        assert len(keys) == 10
    
    def test_hash_api_key(self):
        """Test that API key hashing is deterministic."""
        from app.services.identity.api_keys import hash_api_key
        
        test_key = "manifest_sk_test123456789"
        hash1 = hash_api_key(test_key)
        hash2 = hash_api_key(test_key)
        
        assert hash1 == hash2
        assert len(hash1) == 64


class TestBillingTiers:
    """Tests for billing tier configuration."""
    
    def test_billing_tier_limits(self):
        """Test that all billing tiers have proper limits configured."""
        from app.services.identity.api_keys import BillingTier
        
        assert BillingTier.FREE in BillingTier.LIMITS
        assert BillingTier.STARTER in BillingTier.LIMITS
        assert BillingTier.PRO in BillingTier.LIMITS
        assert BillingTier.ENTERPRISE in BillingTier.LIMITS
        
        for tier, limits in BillingTier.LIMITS.items():
            assert "requests_per_month" in limits
            assert "rate_limit_per_minute" in limits
    
    def test_free_tier_limits(self):
        """Test free tier has expected limits."""
        from app.services.identity.api_keys import BillingTier
        
        free_limits = BillingTier.LIMITS[BillingTier.FREE]
        assert free_limits["requests_per_month"] == 1000
        assert free_limits["rate_limit_per_minute"] == 10
    
    def test_enterprise_unlimited_requests(self):
        """Test enterprise tier has unlimited monthly requests."""
        from app.services.identity.api_keys import BillingTier
        
        enterprise_limits = BillingTier.LIMITS[BillingTier.ENTERPRISE]
        assert enterprise_limits["requests_per_month"] == -1


class TestApiKeyService:
    """Tests for ApiKeyService class."""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database client."""
        mock = MagicMock()
        mock.table.return_value = mock
        mock.select.return_value = mock
        mock.insert.return_value = mock
        mock.update.return_value = mock
        mock.delete.return_value = mock
        mock.eq.return_value = mock
        mock.order.return_value = mock
        mock.single.return_value = mock
        mock.execute.return_value = MagicMock(data={
            "id": "test-client-id",
            "user_id": "test-user-id",
            "name": "Test Client",
            "tier": "free",
            "status": "active"
        })
        return mock
    
    def test_create_api_client(self, mock_db):
        """Test creating an API client."""
        from app.services.identity.api_keys import ApiKeyService
        
        service = ApiKeyService()
        service.db = mock_db
        
        result = service.create_api_client("user-123", "My App", "free")
        
        mock_db.table.assert_called_with("api_clients")
        assert result is not None
    
    def test_create_api_key(self, mock_db):
        """Test creating an API key."""
        from app.services.identity.api_keys import ApiKeyService
        
        mock_db.execute.return_value = MagicMock(data={
            "id": "key-id",
            "client_id": "client-id",
            "name": "Default Key",
            "key_prefix": "manifest_sk_tes",
            "status": "active"
        })
        
        service = ApiKeyService()
        service.db = mock_db
        
        result = service.create_api_key("client-123", "Test Key")
        
        assert "full_key" in result
        assert result["full_key"].startswith("manifest_sk_")
    
    def test_validate_api_key_invalid_format(self, mock_db):
        """Test that invalid key format returns None."""
        from app.services.identity.api_keys import ApiKeyService
        
        service = ApiKeyService()
        service.db = mock_db
        
        result = service.validate_api_key("invalid_key")
        assert result is None
        
        result = service.validate_api_key("")
        assert result is None
        
        result = service.validate_api_key(None)
        assert result is None


class TestApiUsageService:
    """Tests for ApiUsageService class."""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database client."""
        mock = MagicMock()
        mock.table.return_value = mock
        mock.select.return_value = mock
        mock.insert.return_value = mock
        mock.update.return_value = mock
        mock.eq.return_value = mock
        mock.gte.return_value = mock
        mock.single.return_value = mock
        mock.execute.return_value = MagicMock(data=[])
        return mock
    
    def test_check_rate_limit_allowed(self, mock_db):
        """Test rate limit check when under limit."""
        from app.services.identity.api_keys import ApiUsageService
        
        mock_db.execute.return_value = MagicMock(data=[
            {"id": "1"}, {"id": "2"}, {"id": "3"}  # 3 requests in last minute
        ])
        
        service = ApiUsageService()
        service.db = mock_db
        
        # Free tier allows 10 per minute, should be allowed
        result = service.check_rate_limit("client-123", "free")
        assert result is True
    
    def test_check_rate_limit_exceeded(self, mock_db):
        """Test rate limit check when exceeded."""
        from app.services.identity.api_keys import ApiUsageService
        
        # Simulate 15 requests in last minute (exceeds free tier limit of 10)
        mock_db.execute.return_value = MagicMock(data=[{"id": str(i)} for i in range(15)])
        
        service = ApiUsageService()
        service.db = mock_db
        
        result = service.check_rate_limit("client-123", "free")
        assert result is False
    
    def test_check_monthly_limit_allowed(self, mock_db):
        """Test monthly limit check when under limit."""
        from app.services.identity.api_keys import ApiUsageService
        
        mock_db.execute.return_value = MagicMock(data=[
            {"request_count": 100, "tokens_used": 0}
        ])
        
        service = ApiUsageService()
        service.db = mock_db
        
        result = service.check_monthly_limit("client-123", "free")
        assert result is True
    
    def test_check_monthly_limit_enterprise_unlimited(self, mock_db):
        """Test that enterprise tier has no monthly limit."""
        from app.services.identity.api_keys import ApiUsageService
        
        service = ApiUsageService()
        service.db = mock_db
        
        result = service.check_monthly_limit("client-123", "enterprise")
        assert result is True


class TestApiV1Routes:
    """Tests for REST API v1 endpoints."""
    
    @pytest.fixture
    def mock_auth_info(self):
        """Mock authenticated user info."""
        return {
            "key_id": "key-123",
            "client_id": "client-123",
            "user_id": "user-123",
            "tier": "free",
            "limits": {"rate_limit_per_minute": 10, "requests_per_month": 1000}
        }
    
    def test_api_info_endpoint(self):
        """Test the API info endpoint returns correct structure."""
        from app.routes.api_v1_routes import api_info
        import asyncio
        
        result = asyncio.get_event_loop().run_until_complete(api_info())
        
        assert result["name"] == "Manifest API"
        assert result["version"] == "1.0.0"
        assert result["status"] == "operational"
        assert "documentation" in result
    
    def test_format_idea(self):
        """Test idea formatting for API response."""
        from app.routes.api_v1_routes import format_idea
        
        idea = {
            "idea_id": "test-id",
            "title": "Test Idea",
            "description": "A test description",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
            "is_published": True,
            "business_model_canvas": {"data": "test"},
            "pitch_deck": None,
            "product_requirements_document": None,
            "provisional_patent": None
        }
        
        formatted = format_idea(idea)
        
        assert formatted["id"] == "test-id"
        assert formatted["title"] == "Test Idea"
        assert formatted["has_business_model_canvas"] is True
        assert formatted["has_pitch_deck"] is False
        assert formatted["has_prd"] is False
        assert formatted["has_patent"] is False


class TestApiKeyAuth:
    """Tests for API key authentication."""
    
    def test_auth_missing_header(self):
        """Test that missing authorization header returns 401."""
        from app.routes.api_v1_routes import ApiKeyAuth
        from fastapi import HTTPException
        import asyncio
        
        auth = ApiKeyAuth()
        
        with pytest.raises(HTTPException) as exc:
            asyncio.get_event_loop().run_until_complete(auth(None))
        
        assert exc.value.status_code == 401
        assert "missing_api_key" in str(exc.value.detail)
    
    def test_auth_invalid_format(self):
        """Test that invalid authorization format returns 401."""
        from app.routes.api_v1_routes import ApiKeyAuth
        from fastapi import HTTPException
        import asyncio
        
        auth = ApiKeyAuth()
        
        with pytest.raises(HTTPException) as exc:
            asyncio.get_event_loop().run_until_complete(auth("InvalidFormat"))
        
        assert exc.value.status_code == 401
        assert "invalid_format" in str(exc.value.detail)


class TestApiParity:
    """Tests to ensure REST API has parity with GraphQL."""
    
    def test_idea_fields_match_graphql(self):
        """Test that API idea fields match GraphQL schema."""
        from app.routes.api_v1_routes import format_idea
        
        expected_fields = [
            "id", "title", "description", "created_at", "updated_at",
            "is_published", "has_business_model_canvas", "has_pitch_deck",
            "has_prd", "has_patent"
        ]
        
        test_idea = {
            "idea_id": "test",
            "title": "Test",
            "description": None,
            "created_at": None,
            "updated_at": None,
            "is_published": False,
            "business_model_canvas": None,
            "pitch_deck": None,
            "product_requirements_document": None,
            "provisional_patent": None
        }
        
        formatted = format_idea(test_idea)
        
        for field in expected_fields:
            assert field in formatted, f"Missing field: {field}"
    
    def test_error_response_structure(self):
        """Test that error responses follow OpenAI-style format."""
        from app.routes.api_v1_routes import ApiKeyAuth
        from fastapi import HTTPException
        import asyncio
        
        auth = ApiKeyAuth()
        
        with pytest.raises(HTTPException) as exc:
            asyncio.get_event_loop().run_until_complete(auth(None))
        
        error_detail = exc.value.detail
        assert "error" in error_detail
        assert "message" in error_detail["error"]
        assert "type" in error_detail["error"]
        assert "code" in error_detail["error"]
