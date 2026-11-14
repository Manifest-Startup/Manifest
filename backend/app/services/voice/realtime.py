"""OpenAI Realtime (speech-to-speech) session minting for Manifest Voice.

For the lowest possible latency and native barge-in, the browser talks to
OpenAI's Realtime API **directly over WebRTC**. To keep the platform's
the customer's own OpenAI key (bring-your-own-key) server-side, this service mints a short-lived *ephemeral
client secret* that the browser uses only for the WebRTC/SDP handshake; the
secret expires within ~1 minute and cannot be used for anything else.

Cost + safety guardrails (Realtime audio is far more expensive than the
streamed ``tts-1`` pipeline, so this is opt-in and gated):

- Disabled by default. Enable with ``VOICE_REALTIME_ENABLED=true``.
- Requires an OpenAI key for the current user; otherwise it reports itself disabled.
- Guests are refused unless ``VOICE_REALTIME_ALLOW_GUESTS=true``.
- The frontend falls back to the existing streaming pipeline whenever this
  service reports ``enabled=false`` or a mint fails.

See docs/VOICE_AGENT_API.md.
"""

from __future__ import annotations

import os
from typing import Any

import requests
from app.services.ai.credentials import MISSING_KEY_MESSAGE, current_openai_key
from app.services.voice.agent import voice_agent_service

OPENAI_REALTIME_SESSIONS_URL = "https://api.openai.com/v1/realtime/sessions"
DEFAULT_REALTIME_MODEL = "gpt-4o-realtime-preview"
# Realtime exposes a different voice set than the TTS API. `nova` is NOT a
# Realtime voice; `shimmer` is the closest warm, female-presenting default.
DEFAULT_REALTIME_VOICE = "shimmer"
_REQUEST_TIMEOUT_SECONDS = 15

REALTIME_SPOKEN_GUIDANCE = (
    "You are speaking out loud in a live voice conversation. Keep replies short, "
    "warm, and natural—one or two sentences, no lists, no markdown, no spelled-out "
    "punctuation. Ask at most one question at a time and let the founder interrupt you."
)


class RealtimeVoiceError(Exception):
    """Raised when a Realtime session cannot be minted."""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


class RealtimeVoiceService:
    """Mints ephemeral OpenAI Realtime sessions for the browser WebRTC client."""

    # ---- configuration / gating ----

    def is_feature_enabled(self) -> bool:
        return _truthy(os.getenv("VOICE_REALTIME_ENABLED"))

    def allow_guests(self) -> bool:
        return _truthy(os.getenv("VOICE_REALTIME_ALLOW_GUESTS"))

    def is_available(self) -> bool:
        """Feature flag on AND an API key is configured to mint secrets."""
        return self.is_feature_enabled() and bool(current_openai_key())

    def model(self) -> str:
        return (os.getenv("VOICE_REALTIME_MODEL") or "").strip() or DEFAULT_REALTIME_MODEL

    def voice(self) -> str:
        return (os.getenv("VOICE_REALTIME_VOICE") or "").strip() or DEFAULT_REALTIME_VOICE

    # ---- instructions / grounding ----

    def build_instructions(self, context: dict[str, Any] | None) -> str:
        """Compose the strategist persona + spoken guidance + session grounding.

        Reuses the voice agent's shared persona so the Realtime session sounds
        like the same Manifest strategist as the streamed pipeline.
        """
        parts: list[str] = [
            voice_agent_service.BASE_VOICE_AGENT_PROMPT.strip(),
            REALTIME_SPOKEN_GUIDANCE,
        ]

        context = context or {}
        if context.get("landing_onboarding"):
            parts.append(voice_agent_service.LANDING_ONBOARDING_GROUNDING_HINT)
        elif context.get("onboarding_mode"):
            parts.append(voice_agent_service.ONBOARDING_GROUNDING_HINT)

        profile = voice_agent_service._build_profile_context(context.get("user") or {})
        if profile:
            parts.append(f"Founder profile: {profile}")

        idea_title = (context.get("idea_title") or "").strip()
        if idea_title:
            parts.append(f"Current idea title: {idea_title}")
        note_excerpt = (context.get("idea_note_excerpt") or "").strip()
        if note_excerpt:
            parts.append(f"Current working note (do not re-ask what is here):\n{note_excerpt}")

        return "\n\n".join(part for part in parts if part)

    # ---- session minting ----

    def create_session(
        self,
        *,
        context: dict[str, Any] | None = None,
        is_guest: bool = False,
    ) -> dict[str, Any]:
        """Mint an ephemeral Realtime session secret for the browser.

        Returns a dict with ``enabled`` plus, when enabled, ``client_secret``,
        ``expires_at``, ``model``, ``voice`` and the WebRTC ``base_url``.
        Raises :class:`RealtimeVoiceError` only for genuine mint failures so
        the route can distinguish "disabled" (graceful) from "broken" (502).
        """
        if not self.is_feature_enabled():
            return {"enabled": False, "reason": "disabled"}

        api_key = current_openai_key()
        if not api_key:
            return {"enabled": False, "reason": "no_api_key", "message": MISSING_KEY_MESSAGE}

        if is_guest and not self.allow_guests():
            return {"enabled": False, "reason": "guest_blocked"}

        model = self.model()
        voice = self.voice()
        payload = {
            "model": model,
            "voice": voice,
            "modalities": ["audio", "text"],
            "instructions": self.build_instructions(context),
            "input_audio_transcription": {"model": "whisper-1"},
            "turn_detection": {"type": "server_vad"},
        }

        data = self._post_session(api_key=api_key, payload=payload)
        secret = data.get("client_secret") if isinstance(data, dict) else None
        if isinstance(secret, dict):
            value = secret.get("value")
            expires_at = secret.get("expires_at")
        else:
            value = data.get("value") if isinstance(data, dict) else None
            expires_at = data.get("expires_at") if isinstance(data, dict) else None

        if not value:
            raise RealtimeVoiceError("Realtime session response did not include a client secret")

        return {
            "enabled": True,
            "client_secret": value,
            "expires_at": expires_at,
            "model": model,
            "voice": voice,
            "base_url": "https://api.openai.com/v1/realtime",
        }

    def _post_session(self, *, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to OpenAI to create the ephemeral session (isolated for tests)."""
        try:
            response = requests.post(
                OPENAI_REALTIME_SESSIONS_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "OpenAI-Beta": "realtime=v1",
                },
                json=payload,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise RealtimeVoiceError(f"Realtime session request failed: {exc}") from exc

        if response.status_code >= 400:
            raise RealtimeVoiceError(
                f"Realtime session mint returned {response.status_code}: {response.text[:300]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise RealtimeVoiceError("Realtime session response was not valid JSON") from exc


realtime_voice_service = RealtimeVoiceService()
