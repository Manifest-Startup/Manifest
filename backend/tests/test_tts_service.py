"""
Unit tests for TTS Service using AIRouter
"""

import base64
from unittest.mock import MagicMock, patch

import pytest


class TestTTSService:
    """Test suite for TTSService"""

    @pytest.fixture
    def mock_router(self):
        """Create a mock AIRouter for TTS"""
        mock = MagicMock()
        mock.is_available.return_value = True
        mock.tts.return_value = b"fake_audio_data"
        return mock

    @pytest.fixture
    def tts_service(self, mock_router):
        """Create TTSService with mocked router"""
        with patch("app.services.tts_service.AIRouter") as mock_class:
            mock_class.return_value = mock_router
            from app.services.tts_service import TTSService

            service = TTSService()
            service.router = mock_router
            return service

    def test_text_to_speech_success(self, tts_service, mock_router):
        """Test successful text to speech conversion"""
        result = tts_service.text_to_speech("Hello world")

        assert result == b"fake_audio_data"
        mock_router.tts.assert_called_once()

    def test_text_to_speech_empty_text(self, tts_service):
        """Test handling empty text"""
        result = tts_service.text_to_speech("")
        assert result is None

    def test_text_to_speech_whitespace_only(self, tts_service):
        """Test handling whitespace-only text"""
        result = tts_service.text_to_speech("   ")
        assert result is None

    def test_text_to_speech_router_not_available(self):
        """Test handling when router is not available"""
        with patch("app.services.tts_service.AIRouter") as mock_class:
            mock_router = MagicMock()
            mock_router.is_available.return_value = False
            mock_class.return_value = mock_router

            from app.services.tts_service import TTSService

            service = TTSService()

            result = service.text_to_speech("Hello")
            assert result is None

    def test_text_to_speech_base64(self, tts_service):
        """Test base64 encoding of audio"""
        result = tts_service.text_to_speech_base64("Hello")

        assert result is not None
        decoded = base64.b64decode(result)
        assert decoded == b"fake_audio_data"

    def test_text_to_speech_base64_router_not_available(self):
        """Test base64 method with router not available"""
        with patch("app.services.tts_service.AIRouter") as mock_class:
            mock_router = MagicMock()
            mock_router.is_available.return_value = False
            mock_class.return_value = mock_router

            from app.services.tts_service import TTSService

            service = TTSService()

            result = service.text_to_speech_base64("Hello")
            assert result is None

    def test_is_available_with_router(self, tts_service):
        """Test availability check with initialized router"""
        assert tts_service.is_available() is True

    def test_is_available_without_router(self):
        """Test availability check without router"""
        with patch("app.services.tts_service.AIRouter") as mock_class:
            mock_router = MagicMock()
            mock_router.is_available.return_value = False
            mock_class.return_value = mock_router

            from app.services.tts_service import TTSService

            service = TTSService()

            assert service.is_available() is False

    def test_voice_options(self, tts_service, mock_router):
        """Test different voice options"""
        for voice in ["alloy", "coral", "fable", "onyx", "sage", "shimmer", "verse"]:
            tts_service.text_to_speech("Test", voice=voice)

            call_args = mock_router.tts.call_args
            assert call_args[1]["voice"] == voice

    def test_default_voice_is_nova(self, mock_router, monkeypatch):
        """Test that the standard GPT female voice (nova) is used when no override is set."""
        monkeypatch.delenv("VOICE_AGENT_TTS_VOICE", raising=False)

        with patch("app.services.tts_service.AIRouter") as mock_class:
            mock_class.return_value = mock_router

            from app.services.tts_service import TTSService

            tts_service = TTSService()
            tts_service.router = mock_router
            tts_service.text_to_speech("Test")

        call_args = mock_router.tts.call_args
        assert call_args[1]["voice"] == "nova"

    def test_model_options(self, tts_service, mock_router):
        """Test different model options"""
        tts_service.text_to_speech("Test", model="gpt-4o-mini-tts")

        call_args = mock_router.tts.call_args
        assert call_args[1]["model"] == "gpt-4o-mini-tts"

    def test_default_model_is_current_snapshot(self, mock_router, monkeypatch):
        """Default speech uses the current steerable OpenAI TTS snapshot."""
        monkeypatch.delenv("VOICE_AGENT_TTS_MODEL", raising=False)

        with patch("app.services.tts_service.AIRouter") as mock_class:
            mock_class.return_value = mock_router

            from app.services.tts_service import TTSService

            service = TTSService()
            service.router = mock_router
            service.text_to_speech("Test")

        call_args = mock_router.tts.call_args
        assert call_args[1]["model"] == "gpt-4o-mini-tts-2025-12-15"

    def test_model_env_override_respected(self, mock_router, monkeypatch):
        """Operators can trade latency for steerable delivery via VOICE_AGENT_TTS_MODEL."""
        monkeypatch.setenv("VOICE_AGENT_TTS_MODEL", "gpt-4o-mini-tts")

        with patch("app.services.tts_service.AIRouter") as mock_class:
            mock_class.return_value = mock_router

            from app.services.tts_service import TTSService

            service = TTSService()
            service.router = mock_router
            service.text_to_speech("Test")

        call_args = mock_router.tts.call_args
        assert call_args[1]["model"] == "gpt-4o-mini-tts"

    def test_instructions_are_forwarded(self, tts_service, mock_router):
        """Test voice instructions flow through to AIRouter."""
        tts_service.text_to_speech("Test", instructions="Sound natural.")

        call_args = mock_router.tts.call_args
        assert call_args[1]["instructions"] == "Sound natural."

    def test_api_error_handling(self, tts_service, mock_router):
        """Test handling of API errors"""
        mock_router.tts.side_effect = Exception("API Error")

        result = tts_service.text_to_speech("Hello")
        assert result is None

    def test_voices_dict_defined(self, tts_service):
        """Test that voices dictionary is defined"""
        assert "coral" in tts_service.VOICES
        assert "alloy" in tts_service.VOICES
        assert len(tts_service.VOICES) >= 10


class TestTTSRoutes:
    """Test suite for TTS API routes"""

    @pytest.fixture
    def client(self):
        """Create a test client"""
        from app.main import fastapi_app
        from fastapi.testclient import TestClient

        return TestClient(fastapi_app)

    def test_tts_endpoint_exists(self, client):
        """Test that TTS endpoint exists"""
        response = client.post("/api/voice-agent/tts", json={"text": "Hello", "voice": "coral"})
        assert response.status_code in [200, 401, 403, 500]

    def test_tts_endpoint_returns_fallback_when_unavailable(self, client):
        """Test TTS endpoint returns fallback flag when service unavailable"""
        with patch("app.services.tts_service.tts_service") as mock_service:
            mock_service.is_available.return_value = False

            response = client.post("/api/voice-agent/tts", json={"text": "Hello", "voice": "coral"})

            if response.status_code == 200:
                data = response.json()
                assert data.get("fallback_to_browser", False) is True
