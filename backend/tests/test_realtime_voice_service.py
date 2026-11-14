"""Tests for the Realtime (speech-to-speech) session minting service + routes."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def service():
    from app.services.voice.realtime import RealtimeVoiceService

    return RealtimeVoiceService()


class TestRealtimeGating:
    def test_disabled_by_default(self, service, monkeypatch):
        monkeypatch.delenv("VOICE_REALTIME_ENABLED", raising=False)
        assert service.is_feature_enabled() is False
        assert service.is_available() is False

    def test_available_requires_flag_and_key(self, service, monkeypatch):
        monkeypatch.setenv("VOICE_REALTIME_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert service.is_available() is True

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert service.is_available() is False

    def test_create_session_returns_disabled_when_off(self, service, monkeypatch):
        monkeypatch.delenv("VOICE_REALTIME_ENABLED", raising=False)
        result = service.create_session(context={}, is_guest=False)
        assert result == {"enabled": False, "reason": "disabled"}

    def test_create_session_blocks_guests_by_default(self, service, monkeypatch):
        monkeypatch.setenv("VOICE_REALTIME_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("VOICE_REALTIME_ALLOW_GUESTS", raising=False)

        result = service.create_session(context={}, is_guest=True)
        assert result["enabled"] is False
        assert result["reason"] == "guest_blocked"

    def test_create_session_allows_guests_when_opted_in(self, service, monkeypatch):
        monkeypatch.setenv("VOICE_REALTIME_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("VOICE_REALTIME_ALLOW_GUESTS", "true")

        with patch.object(
            service, "_post_session", return_value={"client_secret": {"value": "ek_1", "expires_at": 42}}
        ):
            result = service.create_session(context={}, is_guest=True)
        assert result["enabled"] is True


class TestRealtimeMint:
    @pytest.fixture(autouse=True)
    def _enable(self, monkeypatch):
        monkeypatch.setenv("VOICE_REALTIME_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def test_mints_ephemeral_secret(self, service):
        with patch.object(
            service,
            "_post_session",
            return_value={"client_secret": {"value": "ek_secret", "expires_at": 123}},
        ) as mock_post:
            result = service.create_session(context={"idea_title": "Acme"}, is_guest=False)

        assert result["enabled"] is True
        assert result["client_secret"] == "ek_secret"
        assert result["expires_at"] == 123
        assert result["model"]
        assert result["voice"]
        assert result["base_url"] == "https://api.openai.com/v1/realtime"
        # Instructions carry persona + grounding.
        payload = mock_post.call_args.kwargs["payload"]
        assert "Manifest Voice Strategist" in payload["instructions"]
        assert "Acme" in payload["instructions"]
        assert payload["turn_detection"]["type"] == "server_vad"

    def test_tolerates_flat_secret_shape(self, service):
        with patch.object(
            service, "_post_session", return_value={"value": "ek_flat", "expires_at": 9}
        ):
            result = service.create_session(context={}, is_guest=False)
        assert result["client_secret"] == "ek_flat"

    def test_missing_secret_raises(self, service):
        from app.services.voice.realtime import RealtimeVoiceError

        with patch.object(service, "_post_session", return_value={"client_secret": {}}):
            with pytest.raises(RealtimeVoiceError):
                service.create_session(context={}, is_guest=False)

    def test_model_and_voice_env_overrides(self, service, monkeypatch):
        monkeypatch.setenv("VOICE_REALTIME_MODEL", "gpt-realtime")
        monkeypatch.setenv("VOICE_REALTIME_VOICE", "marin")
        assert service.model() == "gpt-realtime"
        assert service.voice() == "marin"


class TestRealtimeRoutes:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import fastapi_app

        return TestClient(fastapi_app)

    def test_status_requires_auth(self, client):
        response = client.get("/api/voice-agent/realtime/status")
        assert response.status_code in [401, 403, 500]

    def test_status_reports_enabled(self, client):
        from app.main import fastapi_app
        from app.routes import voice_agent_routes
        from app.routes.dependencies import require_user_id

        fastapi_app.dependency_overrides[require_user_id] = lambda: "user-1"
        try:
            with patch.object(
                voice_agent_routes.realtime_voice_service, "is_available", return_value=True
            ), patch.object(voice_agent_routes, "_principal_is_guest", return_value=False):
                response = client.get("/api/voice-agent/realtime/status")
            assert response.status_code == 200
            assert response.json() == {"enabled": True}
        finally:
            fastapi_app.dependency_overrides.pop(require_user_id, None)

    def test_session_mints_when_enabled(self, client):
        from app.main import fastapi_app
        from app.routes import voice_agent_routes
        from app.routes.dependencies import require_user_id

        fastapi_app.dependency_overrides[require_user_id] = lambda: "user-1"
        minted = {
            "enabled": True,
            "client_secret": "ek_x",
            "expires_at": 99,
            "model": "gpt-4o-realtime-preview",
            "voice": "shimmer",
            "base_url": "https://api.openai.com/v1/realtime",
        }
        try:
            with patch.object(
                voice_agent_routes.realtime_voice_service, "is_available", return_value=True
            ), patch.object(
                voice_agent_routes.realtime_voice_service, "create_session", return_value=minted
            ), patch.object(
                voice_agent_routes, "_principal_is_guest", return_value=False
            ), patch.object(
                voice_agent_routes.voice_agent_service, "_load_context", return_value={}
            ), patch.object(
                voice_agent_routes, "create_database_client", return_value=MagicMock()
            ):
                response = client.post("/api/voice-agent/realtime/session", json={})
            assert response.status_code == 200
            body = response.json()
            assert body["enabled"] is True
            assert body["client_secret"] == "ek_x"
        finally:
            fastapi_app.dependency_overrides.pop(require_user_id, None)

    def test_session_disabled_returns_enabled_false(self, client):
        from app.main import fastapi_app
        from app.routes import voice_agent_routes
        from app.routes.dependencies import require_user_id

        fastapi_app.dependency_overrides[require_user_id] = lambda: "user-1"
        try:
            with patch.object(
                voice_agent_routes.realtime_voice_service, "is_available", return_value=False
            ):
                response = client.post("/api/voice-agent/realtime/session", json={})
            assert response.status_code == 200
            assert response.json()["enabled"] is False
        finally:
            fastapi_app.dependency_overrides.pop(require_user_id, None)
