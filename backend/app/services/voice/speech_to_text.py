"""
Speech-to-Text Service using AIRouter.

This lets clients upload short microphone captures when browser-native speech
recognition is unavailable or unreliable.
"""

import base64
import binascii
import os

from app.services.ai.router import AIRouter
from app.utils.logger import logger


class STTService:
    """Speech-to-text service using AIRouter transcription models."""

    DEFAULT_MODEL = AIRouter.DEFAULT_TRANSCRIBE_MODEL

    def __init__(self):
        """Initialize the STT service with AIRouter."""
        logger.info("[STT] Initializing STT service")
        self.router = AIRouter()
        self.default_model = os.getenv("VOICE_AGENT_TRANSCRIBE_MODEL", self.DEFAULT_MODEL)

        if self.router.is_available():
            logger.info("[STT] AIRouter initialized for transcription")
        else:
            logger.warning("[STT] AIRouter not configured")

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: str | None = None,
        mime_type: str | None = None,
        language: str | None = None,
        model: str | None = None,
    ) -> str | None:
        """
        Transcribe audio bytes into text.

        Args:
            audio_bytes: Audio payload
            filename: Optional file name hint
            mime_type: Optional content type hint
            language: Optional language hint
            model: Optional transcription model override

        Returns:
            Transcript text or None if transcription failed
        """
        if not self.router.is_available():
            logger.warning("[STT] AIRouter not available")
            return None

        if not audio_bytes:
            logger.warning("[STT] Empty audio payload provided")
            return None

        try:
            transcript = self.router.transcribe_audio(
                audio_bytes=audio_bytes,
                filename=filename or "voice-input.webm",
                mime_type=mime_type,
                language=language,
                model=model or self.default_model,
            )

            if transcript:
                logger.info("[STT] Transcribed %s characters", len(transcript))

            return transcript
        except Exception as exc:
            logger.error("[STT] Error transcribing audio: %s", exc)
            return None

    def transcribe_base64(
        self,
        audio_base64: str,
        filename: str | None = None,
        mime_type: str | None = None,
        language: str | None = None,
        model: str | None = None,
    ) -> str | None:
        """
        Decode and transcribe a base64 audio payload.

        Args:
            audio_base64: Base64-encoded audio
            filename: Optional file name hint
            mime_type: Optional content type hint
            language: Optional language hint
            model: Optional transcription model override

        Returns:
            Transcript text or None if decoding or transcription failed
        """
        try:
            audio_bytes = base64.b64decode(audio_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            logger.error("[STT] Invalid base64 audio payload: %s", exc)
            return None

        return self.transcribe_audio(
            audio_bytes=audio_bytes,
            filename=filename,
            mime_type=mime_type,
            language=language,
            model=model,
        )

    def is_available(self) -> bool:
        """Check if the STT service is available."""
        return self.router.is_available()


stt_service = STTService()
