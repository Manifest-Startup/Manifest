"""
Text-to-Speech Service using AIRouter.

The backend owns the default OpenAI voice configuration so every client can
consume the same conversational voice without hardcoding model choices in the UI.
"""

import base64
import os

from app.services.ai.router import AIRouter
from app.utils.logger import logger


class TTSService:
    """Text-to-Speech service using AIRouter for natural voice."""

    VOICES = {
        "alloy": "Balanced and neutral",
        "ash": "Steady and grounded",
        "ballad": "Soft and reflective",
        "coral": "Warm and conversational",
        "echo": "Clear and direct",
        "fable": "Expressive and engaging",
        "onyx": "Deep and authoritative",
        "nova": "Friendly and upbeat",
        "sage": "Calm and thoughtful",
        "shimmer": "Light and soothing",
        "verse": "Energetic and polished",
    }

    # Standard GPT female-presenting voice; override with VOICE_AGENT_TTS_VOICE.
    DEFAULT_VOICE = "nova"
    # Latest published GPT-4o mini TTS snapshot, verified 2026-09-12.
    # Sentence chunking and prefetch keep this off the full-response critical path.
    DEFAULT_MODEL = "gpt-4o-mini-tts-2025-12-15"
    DEFAULT_INSTRUCTIONS = AIRouter.DEFAULT_TTS_INSTRUCTIONS

    def __init__(self):
        """Initialize the TTS service with AIRouter."""
        logger.info("[TTS] Initializing TTS service")
        self.router = AIRouter()
        self.default_voice = os.getenv("VOICE_AGENT_TTS_VOICE", self.DEFAULT_VOICE)
        self.default_model = os.getenv("VOICE_AGENT_TTS_MODEL", self.DEFAULT_MODEL)
        self.default_instructions = os.getenv(
            "VOICE_AGENT_TTS_INSTRUCTIONS",
            self.DEFAULT_INSTRUCTIONS,
        )

        if self.router.is_available():
            logger.info("[TTS] AIRouter initialized for TTS")
        else:
            logger.warning("[TTS] AIRouter not configured")

    def text_to_speech(
        self,
        text: str,
        voice: str | None = None,
        model: str | None = None,
        instructions: str | None = None,
    ) -> bytes | None:
        """
        Convert text to speech audio.

        Args:
            text: The text to convert to speech
            voice: Optional voice override
            model: Optional TTS model override
            instructions: Optional speech style override

        Returns:
            Audio bytes in MP3 format, or None if failed
        """
        if not self.router.is_available():
            logger.warning("[TTS] AIRouter not available")
            return None

        if not text or len(text.strip()) == 0:
            logger.warning("[TTS] Empty text provided")
            return None

        selected_voice = voice or self.default_voice
        if selected_voice not in self.VOICES:
            logger.warning(
                "[TTS] Unsupported voice '%s'; falling back to %s",
                selected_voice,
                self.default_voice,
            )
            selected_voice = self.default_voice

        selected_model = model or self.default_model
        selected_instructions = instructions or self.default_instructions

        try:
            audio_bytes = self.router.tts(
                text=text,
                voice=selected_voice,
                model=selected_model,
                instructions=selected_instructions,
            )

            if audio_bytes:
                logger.info(f"[TTS] Generated {len(audio_bytes)} bytes of audio")
            return audio_bytes

        except Exception as e:
            logger.error(f"[TTS] Error generating speech: {e}")
            return None

    def text_to_speech_base64(
        self,
        text: str,
        voice: str | None = None,
        model: str | None = None,
        instructions: str | None = None,
    ) -> str | None:
        """
        Convert text to speech and return as base64-encoded string.

        Args:
            text: The text to convert
            voice: Optional voice override
            model: Optional TTS model override
            instructions: Optional speech style override

        Returns:
            Base64-encoded MP3 audio, or None if failed
        """
        audio_bytes = self.text_to_speech(text, voice, model, instructions)
        if audio_bytes:
            return base64.b64encode(audio_bytes).decode("utf-8")
        return None

    def is_available(self) -> bool:
        """Check if TTS service is available."""
        return self.router.is_available()


tts_service = TTSService()
