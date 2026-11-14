"""
AIRouter - Unified AI API wrapper backed by OpenAI.

This keeps a single backend interface for chat, JSON-mode responses,
streaming, embeddings, text-to-speech, and web search so web and future
mobile clients all consume the same capability boundary.
"""

import asyncio
import json
import os
import time
from collections.abc import Generator
from typing import Any

from app.services.ai_credentials import MissingOpenAIKeyError, current_openai_key
from app.utils.logger import logger
from openai import OpenAI

_MAX_CACHED_CLIENTS = 64  # one OpenAI client per active customer key


class AIRouter:
    """
    Unified AI router using the native OpenAI API.

    The class name stays the same to avoid churn across the backend while the
    provider implementation underneath has been simplified to OpenAI only.
    """

    DEFAULT_CHAT_MODEL = "gpt-4o-mini"
    DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
    DEFAULT_TRANSCRIBE_MODEL = "gpt-4o-transcribe"
    DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
    DEFAULT_WEB_SEARCH_MODEL = "gpt-4o-mini-search-preview"

    # Only the steerable GPT-4o TTS models accept the `instructions` field.
    # The low-latency `tts-1` / `tts-1-hd` models reject it with a 400, so we
    # drop instructions for any model outside this set. This keeps the fast
    # path usable as a drop-in latency win (see VOICE_AGENT_TTS_MODEL).
    INSTRUCTION_CAPABLE_TTS_MODELS = frozenset(
        {
            "gpt-4o-mini-tts",
            "gpt-4o-mini-tts-2025-12-15",
            "gpt-4o-mini-tts-2025-03-20",
            "gpt-4o-tts",
        }
    )
    DEFAULT_TTS_INSTRUCTIONS = (
        "Speak in a warm, female-presenting voice with an executive-assistant quality: "
        "polished, courteous, and easy to listen to. "
        "Use a calm, steady pace, clear articulation, natural intonation, and no slang or hype."
    )

    FALLBACK_MODELS = [
        DEFAULT_CHAT_MODEL,
        "gpt-4.1-mini",
    ]

    TRANSCRIBE_FALLBACK_MODELS = [
        DEFAULT_TRANSCRIBE_MODEL,
        "gpt-4o-mini-transcribe",
        "whisper-1",
    ]

    WEB_SEARCH_FALLBACK_MODELS = [
        DEFAULT_WEB_SEARCH_MODEL,
        "gpt-4o-search-preview",
    ]

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
        timeout: float = 60.0,
    ):
        """
        Initialize AIRouter with OpenAI credentials.

        Args:
            api_key: Pin a specific OpenAI key; by default the current user's own key is used
            model: Default model to use
            max_retries: Number of retries on failure
            timeout: Request timeout in seconds
        """
        # An explicit key pins this router (tests, scripts). Otherwise the key is
        # resolved per call: the signed-in user's own key, else the platform key.
        self._explicit_key = api_key
        env_model = (os.getenv("AI_MODEL") or "").strip()
        self.model = model or (env_model or self.DEFAULT_CHAT_MODEL)
        self.max_retries = max_retries
        self.timeout = timeout

        self._clients: dict[str, OpenAI] = {}
        self._client: OpenAI | None = None  # injected client (tests, scripts) wins

    @property
    def api_key(self) -> str | None:
        return self._explicit_key or current_openai_key()

    @api_key.setter
    def api_key(self, value: str | None) -> None:
        self._explicit_key = value

    @property
    def client(self) -> OpenAI:
        """OpenAI client for the key in effect (one cached client per key)."""
        if self._client is not None:
            return self._client
        key = self.api_key
        if not key:
            raise MissingOpenAIKeyError()
        client = self._clients.get(key)
        if client is None:
            if len(self._clients) >= _MAX_CACHED_CLIENTS:
                self._clients.pop(next(iter(self._clients))).close()
            client = OpenAI(api_key=key, timeout=self.timeout, max_retries=0)
            self._clients[key] = client
        return client

    def is_available(self) -> bool:
        """True when an OpenAI key is available for the current user or platform."""
        return bool(self.api_key)

    def chat(
        self,
        prompt: str | list[dict[str, str]],
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        response_format: dict[str, str] | None = None,
    ) -> str:
        """
        Send a chat completion request.

        Args:
            prompt: User message string or list of messages
            model: Model to use (overrides default)
            system_prompt: Optional system message
            temperature: Creativity (0-1)
            max_tokens: Maximum response length
            response_format: Optional format specification

        Returns:
            AI response text
        """
        if not self.is_available():
            raise MissingOpenAIKeyError()

        messages = self._prepare_messages(prompt, system_prompt)
        candidate_models = self._candidate_models(model or self.model, self.FALLBACK_MODELS)
        last_error: Exception | None = None

        for attempt in range(max(self.max_retries, 1)):
            current_model = candidate_models[min(attempt, len(candidate_models) - 1)]

            try:
                payload: dict[str, Any] = {
                    "model": current_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }

                if response_format:
                    payload["response_format"] = response_format

                logger.info(
                    "[AIRouter] Chat request to %s (attempt %s)", current_model, attempt + 1
                )
                result = self.client.chat.completions.create(**payload)
                message = result.choices[0].message
                content = self._extract_message_text(message.content) or message.refusal

                if not content:
                    raise RuntimeError("OpenAI chat response did not contain text content.")

                usage = getattr(result, "usage", None)
                self._log_cache_usage(usage, current_model)
                try:
                    from app.services.llm_usage_tap import set_last_usage

                    set_last_usage(current_model, usage)
                except Exception:  # pragma: no cover — tap must never break a call
                    pass
                logger.info("[AIRouter] Response received (%s chars)", len(content))
                return content

            except Exception as exc:
                last_error = exc
                logger.error("[AIRouter] Chat error (attempt %s): %s", attempt + 1, exc)
                if attempt < max(self.max_retries, 1) - 1:
                    time.sleep(2**attempt)

        raise RuntimeError(
            f"Chat request failed after {max(self.max_retries, 1)} attempts: {last_error}"
        )

    def chat_json(
        self,
        prompt: str | list[dict[str, str]],
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """
        Chat with JSON response format.

        Args:
            prompt: User message or messages
            model: Model to use
            system_prompt: Optional system prompt
            temperature: Creativity level

        Returns:
            Parsed JSON response
        """
        json_system = (system_prompt or "").strip()
        if json_system:
            json_system += "\n\n"
        json_system += "Respond with valid JSON only."

        response = self.chat(
            prompt=prompt,
            model=model,
            system_prompt=json_system,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            return json.loads(cleaned.strip())

    async def achat(
        self,
        prompt: str | list[dict[str, str]],
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        response_format: dict[str, str] | None = None,
    ) -> str:
        """Async wrapper around :meth:`chat`.

        Runs the blocking OpenAI request in a worker thread so a 10-30s LLM
        call does not stall the event loop (one slow call would otherwise
        freeze the whole async worker). Reuses the sync path verbatim, so all
        retry, model-fallback, and usage-logging behaviour is identical.
        """
        return await asyncio.to_thread(
            self.chat,
            prompt,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    async def achat_json(
        self,
        prompt: str | list[dict[str, str]],
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Async wrapper around :meth:`chat_json` (see :meth:`achat`)."""
        return await asyncio.to_thread(
            self.chat_json,
            prompt,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
        )

    def chat_stream(
        self,
        prompt: str | list[dict[str, str]],
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.55,
        max_tokens: int = 400,
    ) -> Generator[str, None, None]:
        """
        Stream a chat completion response.

        Args:
            prompt: User message or messages
            model: Model to use
            system_prompt: Optional system prompt
            temperature: Creativity level
            max_tokens: Maximum response length

        Yields:
            Response text chunks
        """
        if not self.is_available():
            raise MissingOpenAIKeyError()

        messages = self._prepare_messages(prompt, system_prompt)
        candidate_models = self._candidate_models(model or self.model, self.FALLBACK_MODELS)
        last_error: Exception | None = None

        for attempt in range(max(self.max_retries, 1)):
            current_model = candidate_models[min(attempt, len(candidate_models) - 1)]
            logger.info(
                "[AIRouter] Stream request to %s (attempt %s, temperature=%s, max_tokens=%s)",
                current_model,
                attempt + 1,
                temperature,
                max_tokens,
            )

            try:
                stream = self.client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                )

                for chunk in stream:
                    # The terminal usage chunk has no choices but does carry
                    # `usage` (only when stream_options.include_usage is set).
                    if not chunk.choices:
                        usage = getattr(chunk, "usage", None)
                        if usage is not None:
                            self._log_cache_usage(usage, current_model)
                            try:
                                from app.services.llm_usage_tap import set_last_usage

                                set_last_usage(current_model, usage)
                            except Exception:  # pragma: no cover
                                pass
                        continue

                    delta = chunk.choices[0].delta
                    content = self._extract_message_text(getattr(delta, "content", None))
                    if content:
                        yield content
                return
            except Exception as exc:
                last_error = exc
                logger.error("[AIRouter] Stream error (attempt %s): %s", attempt + 1, exc)
                if attempt < max(self.max_retries, 1) - 1:
                    time.sleep(2**attempt)

        raise RuntimeError(
            f"Streaming chat request failed after {max(self.max_retries, 1)} attempts: {last_error}"
        )

    def embed(
        self,
        text: str | list[str],
        model: str | None = None,
    ) -> list[list[float]]:
        """
        Generate embeddings for text.

        Args:
            text: Single string or list of strings to embed
            model: Embedding model to use

        Returns:
            List of embedding vectors
        """
        if not self.is_available():
            raise MissingOpenAIKeyError()

        inputs = [text] if isinstance(text, str) else text
        current_model = model or self.DEFAULT_EMBEDDING_MODEL

        logger.info("[AIRouter] Embedding %s text(s) with %s", len(inputs), current_model)
        result = self.client.embeddings.create(model=current_model, input=inputs)
        embeddings = [item.embedding for item in result.data]

        logger.info("[AIRouter] Generated %s embeddings", len(embeddings))
        return embeddings

    def tts(
        self,
        text: str,
        voice: str = "nova",
        model: str = DEFAULT_TTS_MODEL,
        response_format: str = "mp3",
        instructions: str | None = None,
    ) -> bytes | None:
        """
        Convert text to speech.

        Args:
            text: Text to convert
            voice: Voice to use
            model: TTS model
            response_format: Audio format
            instructions: Optional voice delivery instructions

        Returns:
            Audio bytes or None if failed
        """
        if not self.is_available():
            logger.warning("[AIRouter] TTS unavailable - no API key")
            return None

        if not text or len(text.strip()) == 0:
            logger.warning("[AIRouter] Empty text for TTS")
            return None

        if len(text) > 4096:
            text = text[:4096]
            logger.warning("[AIRouter] TTS text truncated to 4096 chars")

        try:
            logger.info(
                "[AIRouter] TTS request: %s chars, voice=%s, model=%s", len(text), voice, model
            )

            payload: dict[str, Any] = {
                "model": model,
                "voice": voice,
                "input": text,
                "response_format": response_format,
            }

            # `instructions` is only honored by the steerable GPT-4o TTS models.
            # Forwarding it to tts-1/tts-1-hd raises a 400, so skip it there and
            # let the low-latency models run with their native delivery.
            if instructions and model in self.INSTRUCTION_CAPABLE_TTS_MODELS:
                payload["instructions"] = instructions

            response = self.client.audio.speech.create(**payload)
            audio_bytes = response.content

            logger.info("[AIRouter] TTS generated %s bytes", len(audio_bytes))
            return audio_bytes

        except Exception as exc:
            logger.error("[AIRouter] TTS error: %s", exc)
            return None

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: str = "voice-input.webm",
        mime_type: str | None = None,
        model: str | None = None,
        language: str | None = "en",
    ) -> str | None:
        """
        Convert recorded audio into plain text.

        Args:
            audio_bytes: Binary audio payload
            filename: File name sent to the API
            mime_type: Optional content type
            model: Optional transcription model override
            language: Optional BCP-47 language hint

        Returns:
            Transcript text or None if transcription failed
        """
        if not self.is_available():
            logger.warning("[AIRouter] Transcription unavailable - no API key")
            return None

        if not audio_bytes:
            logger.warning("[AIRouter] Empty audio payload for transcription")
            return None

        candidate_models = self._candidate_models(
            model or os.getenv("VOICE_AGENT_TRANSCRIBE_MODEL", self.DEFAULT_TRANSCRIBE_MODEL),
            self.TRANSCRIBE_FALLBACK_MODELS,
        )
        last_error: Exception | None = None

        for attempt in range(max(self.max_retries, 1)):
            current_model = candidate_models[min(attempt, len(candidate_models) - 1)]

            try:
                logger.info(
                    "[AIRouter] Transcription request to %s (attempt %s, %s bytes)",
                    current_model,
                    attempt + 1,
                    len(audio_bytes),
                )
                result = self.client.audio.transcriptions.create(
                    model=current_model,
                    file=(filename, audio_bytes, mime_type or "application/octet-stream"),
                    language=language or "en",
                    response_format="text",
                )

                transcript = str(result).strip()
                if transcript:
                    logger.info("[AIRouter] Transcription completed (%s chars)", len(transcript))
                    return transcript

                raise RuntimeError("OpenAI transcription response was empty.")

            except Exception as exc:
                last_error = exc
                logger.error("[AIRouter] Transcription error (attempt %s): %s", attempt + 1, exc)
                if attempt < max(self.max_retries, 1) - 1:
                    time.sleep(2**attempt)

        logger.error("[AIRouter] Transcription failed after retries: %s", last_error)
        return None

    def _prepare_messages(
        self,
        prompt: str | list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        """Prepare messages array from various input formats."""
        if isinstance(prompt, str):
            messages: list[dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            return messages

        messages = list(prompt)

        if system_prompt:
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = system_prompt + "\n\n" + messages[0]["content"]
            else:
                messages.insert(0, {"role": "system", "content": system_prompt})

        return messages

    def web_search(
        self,
        query: str,
        model: str | None = None,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """
        Perform a web search using OpenAI's search-preview models.

        Args:
            query: Search query string
            model: Model to use
            max_tokens: Maximum response length

        Returns:
            Dict with 'content' (search results) and 'citations' (sources)
        """
        if not self.is_available():
            raise MissingOpenAIKeyError()

        search_model = model or os.getenv("WEB_SEARCH_MODEL", self.DEFAULT_WEB_SEARCH_MODEL)
        candidate_models = self._candidate_models(search_model, self.WEB_SEARCH_FALLBACK_MODELS)
        last_error: Exception | None = None

        for attempt in range(max(self.max_retries, 1)):
            current_model = candidate_models[min(attempt, len(candidate_models) - 1)]

            try:
                logger.info(
                    "[AIRouter] Web search request to %s (attempt %s)", current_model, attempt + 1
                )
                result = self.client.chat.completions.create(
                    model=current_model,
                    messages=[{"role": "user", "content": query}],
                    max_tokens=max_tokens,
                    web_search_options={},
                )

                message = result.choices[0].message
                content = self._extract_message_text(message.content) or message.refusal or ""
                citation_details = self._extract_url_citations(message.annotations or [])
                citations = [citation["url"] for citation in citation_details]

                logger.info(
                    "[AIRouter] Web search completed (%s chars, %s citations)",
                    len(content),
                    len(citations),
                )

                return {
                    "content": content,
                    "citations": citations,
                    "citation_details": citation_details,
                }

            except Exception as exc:
                last_error = exc
                logger.error("[AIRouter] Web search error (attempt %s): %s", attempt + 1, exc)
                if attempt < max(self.max_retries, 1) - 1:
                    time.sleep(2**attempt)

        raise RuntimeError(
            f"Web search failed after {max(self.max_retries, 1)} attempts: {last_error}"
        )

    def web_search_json(
        self,
        query: str,
        model: str | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """
        Perform a grounded web search and request a JSON response.

        Returns:
            Dict with parsed 'content' plus citation URLs/details.
        """
        if not self.is_available():
            raise MissingOpenAIKeyError()

        search_model = model or os.getenv("WEB_SEARCH_MODEL", self.DEFAULT_WEB_SEARCH_MODEL)
        candidate_models = self._candidate_models(search_model, self.WEB_SEARCH_FALLBACK_MODELS)
        last_error: Exception | None = None
        messages = self._prepare_messages(query, system_prompt)

        for attempt in range(max(self.max_retries, 1)):
            current_model = candidate_models[min(attempt, len(candidate_models) - 1)]

            try:
                logger.info(
                    "[AIRouter] Web search JSON request to %s (attempt %s)",
                    current_model,
                    attempt + 1,
                )
                result = self.client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    web_search_options={},
                )

                message = result.choices[0].message
                content = self._extract_message_text(message.content) or message.refusal or ""
                parsed_content = self._parse_json_content(content)
                citation_details = self._extract_url_citations(message.annotations or [])
                citations = [citation["url"] for citation in citation_details]

                logger.info(
                    "[AIRouter] Web search JSON completed (%s citations)",
                    len(citations),
                )

                return {
                    "content": parsed_content,
                    "citations": citations,
                    "citation_details": citation_details,
                }

            except Exception as exc:
                last_error = exc
                logger.error("[AIRouter] Web search JSON error (attempt %s): %s", attempt + 1, exc)
                if attempt < max(self.max_retries, 1) - 1:
                    time.sleep(2**attempt)

        raise RuntimeError(
            f"Web search JSON failed after {max(self.max_retries, 1)} attempts: {last_error}"
        )

    def health_check(self) -> bool:
        """Perform a health check to verify API connectivity."""
        try:
            response = self.chat("Say OK", max_tokens=10)
            return "OK" in response or len(response) > 0
        except Exception as exc:
            logger.error("[AIRouter] Health check failed: %s", exc)
            return False

    def close(self):
        """Close the OpenAI client."""
        if self._client is not None:
            self._clients.setdefault("__injected__", self._client)
            self._client = None
        for client in self._clients.values():
            try:
                client.close()
            except Exception as exc:
                logger.debug("[AIRouter] Error while closing OpenAI client: %s", exc)
        self._clients.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def _log_cache_usage(usage: Any, model: str) -> None:
        """Emit a cache-hit observability line from an OpenAI usage object.

        OpenAI's auto prompt-prefix cache returns `prompt_tokens_details.cached_tokens`
        on every chat completion. Logging it gives us visibility into how
        well the voice agent's shared prompt prefix is working.
        """
        if usage is None:
            return
        try:
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            details = getattr(usage, "prompt_tokens_details", None)
            cached_tokens = 0
            if details is not None:
                cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)
            elif isinstance(usage, dict):
                cached_tokens = int(
                    ((usage.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
                )
            ratio = (cached_tokens / prompt_tokens) if prompt_tokens else 0.0
            logger.info(
                "[AIRouter] cache: model=%s prompt_tokens=%s cached_tokens=%s ratio=%.2f",
                model,
                prompt_tokens,
                cached_tokens,
                ratio,
            )
        except Exception as exc:
            logger.debug("[AIRouter] cache usage log skipped: %s", exc)

    @staticmethod
    def _candidate_models(primary: str, fallbacks: list[str]) -> list[str]:
        """Return a de-duplicated model preference order."""
        models: list[str] = []
        for candidate in [primary, *fallbacks]:
            if candidate and candidate not in models:
                models.append(candidate)
        return models

    @staticmethod
    def _extract_message_text(content: Any) -> str | None:
        """Normalize SDK content payloads into plain text."""
        if content is None:
            return None

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue

                text = None
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                else:
                    text = getattr(item, "text", None) or getattr(item, "content", None)

                if text:
                    parts.append(str(text))

            normalized = "".join(parts).strip()
            return normalized or None

        return str(content)

    @staticmethod
    def _extract_url_citations(annotations: list[Any]) -> list[dict[str, Any]]:
        """Normalize URL citation annotations into simple dicts."""
        citations: list[dict[str, Any]] = []
        seen = set()

        for annotation in annotations or []:
            citation = getattr(annotation, "url_citation", None)
            url = getattr(citation, "url", None)
            if not url or url in seen:
                continue

            seen.add(url)
            citations.append(
                {
                    "url": url,
                    "title": getattr(citation, "title", None),
                    "start_index": getattr(citation, "start_index", None),
                    "end_index": getattr(citation, "end_index", None),
                }
            )

        return citations

    @staticmethod
    def _parse_json_content(content: str) -> dict[str, Any]:
        """Parse JSON content, tolerating fenced code blocks."""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            cleaned = content.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            return json.loads(cleaned.strip())


ai_router = AIRouter()
