"""
Tests for AIRouter - the shared OpenAI provider wrapper used across Manifest.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _chat_response(content="Hello", annotations=None, refusal=None):
    message = SimpleNamespace(content=content, annotations=annotations, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _stream_chunk(content):
    delta = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _embedding_response(vectors):
    return SimpleNamespace(data=[SimpleNamespace(embedding=vector) for vector in vectors])


def _audio_response(payload=b"audio-bytes"):
    return SimpleNamespace(content=payload)


def _url_annotation(url, title="Example"):
    citation = SimpleNamespace(url=url, title=title, start_index=0, end_index=1)
    return SimpleNamespace(type="url_citation", url_citation=citation)


class TestAIRouterConfig:
    """Configuration and initialization behavior."""

    def test_init_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            from app.services.ai_router import AIRouter

            router = AIRouter(api_key=None)
            assert not router.is_available()

    def test_init_with_explicit_api_key(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        assert router.is_available()
        assert router.api_key == "test-key"

    def test_init_with_env_api_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-test-key"}):
            from app.services.ai_router import AIRouter

            router = AIRouter()
            assert router.api_key == "env-test-key"

    def test_custom_model_is_respected(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test", model="gpt-4.1-mini")
        assert router.model == "gpt-4.1-mini"

    def test_default_model(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test")
        assert router.model == "gpt-4o-mini"

    def test_prepare_messages_from_string(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test")
        messages = router._prepare_messages("Hello", system_prompt="You are helpful.")

        assert messages == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]

    def test_prepare_messages_from_list_with_system_prompt(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test")
        messages = router._prepare_messages(
            [{"role": "user", "content": "Hello"}],
            system_prompt="System",
        )

        assert messages[0]["role"] == "system"
        assert "System" in messages[0]["content"]

    def test_close_releases_client(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test")
        mock_client = MagicMock()
        router._client = mock_client

        router.close()

        mock_client.close.assert_called_once()
        assert router._client is None


class TestAIRouterChat:
    """Chat and JSON-mode behavior."""

    def test_chat_requires_configuration(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key=None)
        router.api_key = None

        with pytest.raises(RuntimeError, match="OpenAI API key"):
            router.chat("Hello")

    def test_chat_success(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.chat.completions.create.return_value = _chat_response("Hello back!")

        result = router.chat("Hello")

        assert result == "Hello back!"
        call_kwargs = router._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["messages"] == [{"role": "user", "content": "Hello"}]

    def test_chat_uses_response_format_when_provided(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.chat.completions.create.return_value = _chat_response('{"ok": true}')

        router.chat("Return JSON", response_format={"type": "json_object"})

        call_kwargs = router._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_chat_retries_on_failure(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key", max_retries=2)
        router._client = MagicMock()
        router._client.chat.completions.create.side_effect = [
            RuntimeError("temporary failure"),
            _chat_response("Recovered"),
        ]

        with patch("app.services.ai_router.time.sleep") as sleep:
            result = router.chat("Hello")

        assert result == "Recovered"
        assert router._client.chat.completions.create.call_count == 2
        sleep.assert_called_once()

    def test_chat_json_success(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.chat.completions.create.return_value = _chat_response('{"key": "value"}')

        assert router.chat_json("Return JSON") == {"key": "value"}

    def test_chat_json_handles_code_block_wrapped_json(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        with patch.object(router, "chat", return_value='```json\n{"key": "value"}\n```'):
            assert router.chat_json("Return JSON") == {"key": "value"}

    def test_chat_stream_yields_chunks(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.chat.completions.create.return_value = [
            _stream_chunk("Hello"),
            _stream_chunk(" world"),
            _stream_chunk(None),
        ]

        assert list(router.chat_stream("Hi")) == ["Hello", " world"]


class TestAIRouterEmbeddings:
    """Embedding behavior."""

    def test_embed_requires_configuration(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key=None)
        router.api_key = None

        with pytest.raises(RuntimeError, match="OpenAI API key"):
            router.embed("Hello")

    def test_embed_single_text(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.embeddings.create.return_value = _embedding_response([[0.1, 0.2, 0.3]])

        assert router.embed("Hello") == [[0.1, 0.2, 0.3]]

    def test_embed_multiple_texts(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.embeddings.create.return_value = _embedding_response([[0.1], [0.2]])

        result = router.embed(["Hello", "World"])

        assert len(result) == 2
        call_kwargs = router._client.embeddings.create.call_args.kwargs
        assert call_kwargs["input"] == ["Hello", "World"]


class TestAIRouterTTS:
    """Text-to-speech behavior."""

    def test_tts_requires_configuration(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key=None)
        router.api_key = None

        assert router.tts("Hello") is None

    def test_tts_returns_none_for_empty_text(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")

        assert router.tts("") is None
        assert router.tts("   ") is None

    @pytest.mark.parametrize("model", ["gpt-4o-mini-tts", "gpt-4o-mini-tts-2025-12-15"])
    def test_tts_success(self, model):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.audio.speech.create.return_value = _audio_response(b"audio-bytes")

        result = router.tts(
            "Hello world",
            voice="coral",
            model=model,
            instructions="Warm and conversational",
        )

        assert result == b"audio-bytes"
        call_kwargs = router._client.audio.speech.create.call_args.kwargs
        assert call_kwargs["voice"] == "coral"
        assert call_kwargs["model"] == model
        assert call_kwargs["instructions"] == "Warm and conversational"

    def test_tts_truncates_long_text(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.audio.speech.create.return_value = _audio_response()

        router.tts("a" * 5000)

        call_kwargs = router._client.audio.speech.create.call_args.kwargs
        assert len(call_kwargs["input"]) == 4096

    def test_tts_omits_instructions_for_low_latency_model(self):
        """tts-1 rejects `instructions`; the router must drop it so the fast path works."""
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.audio.speech.create.return_value = _audio_response(b"audio-bytes")

        result = router.tts(
            "Hello world",
            voice="nova",
            model="tts-1",
            instructions="Warm and conversational",
        )

        assert result == b"audio-bytes"
        call_kwargs = router._client.audio.speech.create.call_args.kwargs
        assert call_kwargs["model"] == "tts-1"
        assert "instructions" not in call_kwargs

    def test_tts_default_voice_is_nova(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.audio.speech.create.return_value = _audio_response()

        router.tts("Hello world")

        call_kwargs = router._client.audio.speech.create.call_args.kwargs
        assert call_kwargs["voice"] == "nova"


class TestAIRouterWebSearch:
    """Web search behavior."""

    def test_web_search_requires_configuration(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key=None)
        router.api_key = None

        with pytest.raises(RuntimeError, match="OpenAI API key"):
            router.web_search("test query")

    def test_web_search_success(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.chat.completions.create.return_value = _chat_response(
            "Search results here",
            annotations=[_url_annotation("https://example.com")],
        )

        result = router.web_search("test query")

        assert result["content"] == "Search results here"
        assert result["citations"] == ["https://example.com"]
        assert result["citation_details"][0]["title"] == "Example"
        call_kwargs = router._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini-search-preview"
        assert call_kwargs["web_search_options"] == {}

    def test_web_search_json_success(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.chat.completions.create.return_value = _chat_response(
            '{"comparables": [], "research_topics": []}',
            annotations=[_url_annotation("https://example.com/report", title="Example Report")],
        )

        result = router.web_search_json("test query", system_prompt="Return JSON")

        assert result["content"] == {"comparables": [], "research_topics": []}
        assert result["citations"] == ["https://example.com/report"]
        assert result["citation_details"][0]["title"] == "Example Report"
        call_kwargs = router._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}
        assert call_kwargs["web_search_options"] == {}

    def test_web_search_custom_model(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.chat.completions.create.return_value = _chat_response("Results")

        router.web_search("query", model="gpt-4o-search-preview")

        call_kwargs = router._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-search-preview"

    def test_web_search_retries_on_failure(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key", max_retries=2)
        router._client = MagicMock()
        router._client.chat.completions.create.side_effect = [
            RuntimeError("temporary failure"),
            _chat_response("Recovered"),
        ]

        with patch("app.services.ai_router.time.sleep") as sleep:
            result = router.web_search("query")

        assert result["content"] == "Recovered"
        assert router._client.chat.completions.create.call_count == 2
        sleep.assert_called_once()


class TestAIRouterHealthCheck:
    """Health checks should be lightweight and defensive."""

    def test_health_check_success(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        with patch.object(router, "chat", return_value="OK"):
            assert router.health_check() is True

    def test_health_check_failure(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        with patch.object(router, "chat", side_effect=RuntimeError("boom")):
            assert router.health_check() is False


class TestAIRouterModels:
    """Model defaults should stay OpenAI-only."""

    def test_default_models_defined(self):
        from app.services.ai_router import AIRouter

        assert AIRouter.DEFAULT_CHAT_MODEL == "gpt-4o-mini"
        assert AIRouter.DEFAULT_EMBEDDING_MODEL == "text-embedding-3-small"
        assert AIRouter.DEFAULT_TTS_MODEL == "gpt-4o-mini-tts"
        assert AIRouter.DEFAULT_WEB_SEARCH_MODEL == "gpt-4o-mini-search-preview"

    def test_fallback_models_are_openai_only(self):
        from app.services.ai_router import AIRouter

        assert AIRouter.FALLBACK_MODELS == ["gpt-4o-mini", "gpt-4.1-mini"]
        assert AIRouter.WEB_SEARCH_FALLBACK_MODELS == [
            "gpt-4o-mini-search-preview",
            "gpt-4o-search-preview",
        ]


class TestAIRouterIntegration:
    """Optional live tests when a real OpenAI key is present."""

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "sk-test-openai-key",
        reason="OPENAI_API_KEY not set for live chat",
    )
    def test_real_chat(self):
        from app.services.ai_router import AIRouter

        router = AIRouter()
        response = router.chat("Say test and nothing else.", max_tokens=10)

        assert len(response) > 0

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "sk-test-openai-key",
        reason="OPENAI_API_KEY not set for live health check",
    )
    def test_real_health_check(self):
        from app.services.ai_router import AIRouter

        router = AIRouter()
        assert isinstance(router.health_check(), bool)


class TestAIRouterSingleton:
    """Singleton availability."""

    def test_singleton_exists(self):
        from app.services.ai_router import ai_router

        assert ai_router is not None

    def test_singleton_is_airouter(self):
        from app.services.ai_router import AIRouter, ai_router

        assert isinstance(ai_router, AIRouter)


class TestAIRouterAsync:
    """The async wrappers must reuse the sync logic and free the event loop."""

    @pytest.mark.asyncio
    async def test_achat_returns_chat_result(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.chat.completions.create.return_value = _chat_response("async hi")

        result = await router.achat("Hello")

        assert result == "async hi"

    @pytest.mark.asyncio
    async def test_achat_delegates_to_sync_chat_with_options(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        with patch.object(router, "chat", return_value="delegated") as mock_chat:
            result = await router.achat("Hi", temperature=0.9, max_tokens=10)

        assert result == "delegated"
        assert mock_chat.call_args.args[0] == "Hi"
        assert mock_chat.call_args.kwargs["temperature"] == 0.9
        assert mock_chat.call_args.kwargs["max_tokens"] == 10

    @pytest.mark.asyncio
    async def test_achat_json_parses_response(self):
        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")
        router._client = MagicMock()
        router._client.chat.completions.create.return_value = _chat_response('{"ok": true}')

        result = await router.achat_json("Return JSON")

        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_achat_does_not_block_event_loop(self):
        """The whole point: a slow sync chat must run in a thread so a
        concurrent coroutine keeps making progress instead of freezing."""
        import asyncio
        import time

        from app.services.ai_router import AIRouter

        router = AIRouter(api_key="test-key")

        def slow_chat(*_args, **_kwargs):
            time.sleep(0.2)
            return "slow"

        ticks = 0

        async def ticker():
            nonlocal ticks
            for _ in range(10):
                await asyncio.sleep(0.02)
                ticks += 1

        with patch.object(router, "chat", side_effect=slow_chat):
            result, _ = await asyncio.gather(router.achat("hi"), ticker())

        assert result == "slow"
        # If achat had blocked the loop, the ticker couldn't have advanced.
        assert ticks >= 5
