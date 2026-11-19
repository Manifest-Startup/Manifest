"""Voice Agent API routes."""

import json
from collections.abc import Generator
from typing import Any

from app.db.database import create_database_client
from app.routes.dependencies import require_user_id
from app.services.voice.agent import voice_agent_service
from app.services.voice.command_catalog import (
    VOICE_COMMAND_CAPABILITIES,
    VOICE_COMMAND_CAPABILITY_SUMMARY,
)
from app.services.voice.speech_to_text import stt_service
from app.services.voice.text_to_speech import tts_service
from app.utils.logger import logger
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/voice-agent", tags=["voice-agent"])


class ConversationMessage(BaseModel):
    role: str
    content: str


class StartConversationRequest(BaseModel):
    idea_id: str | None = None
    """When true, first assistant turn and prompts orient new visitors / guest tryouts."""
    onboarding_mode: bool = False
    """When true with onboarding_mode, use the two-question voice-first landing script."""
    landing_onboarding: bool = False


class ProcessMessageRequest(BaseModel):
    messages: list[ConversationMessage]
    user_message: str
    idea_id: str | None = None
    onboarding_mode: bool = False
    landing_onboarding: bool = False


class QualifyIdeaRequest(BaseModel):
    messages: list[ConversationMessage]
    idea_id: str | None = None


class VoiceAgentResponse(BaseModel):
    message: str
    is_qualified: bool
    summary: str | None = None
    suggested_title: str | None = None
    transcript: str | None = None
    voice_note_html: str | None = None
    covered_topics: list[str] = Field(default_factory=list)
    missing_topics: list[str] = Field(default_factory=list)
    qualification_confidence: float = 0.0
    context: dict[str, Any] = Field(default_factory=dict)
    landing_onboarding_step: int | None = None
    landing_complete: bool = False


class VoiceCommandCapability(BaseModel):
    id: str
    category: str
    title: str
    description: str
    examples: list[str] = Field(default_factory=list)


class VoiceCapabilitiesResponse(BaseModel):
    summary: str
    commands: list[VoiceCommandCapability] = Field(default_factory=list)


class ProcessMessageResponse(BaseModel):
    response: VoiceAgentResponse
    messages: list[dict]


class QualifyIdeaResponse(BaseModel):
    title: str
    description: str
    summary: str | None = None


@router.get("/capabilities", response_model=VoiceCapabilitiesResponse)
async def get_voice_capabilities(user_id: str = Depends(require_user_id)):
    """Return the supported deterministic app-control voice commands."""
    logger.info(f"[VoiceAgentRoutes] Returning capabilities for user: {user_id}")
    return VoiceCapabilitiesResponse(
        summary=VOICE_COMMAND_CAPABILITY_SUMMARY,
        commands=[VoiceCommandCapability(**item) for item in VOICE_COMMAND_CAPABILITIES],
    )


# NOTE: the handlers below are deliberately `def`, not `async def`. They make
# blocking calls (sync DB reads, OpenAI chat/TTS/Whisper round-trips of
# 0.5-3s). FastAPI runs sync handlers in its threadpool, so a slow voice turn
# no longer stalls the event loop — with async handlers one voice request
# froze every other request on the worker for the duration of the OpenAI call.


@router.post("/start")
def start_conversation(
    body: StartConversationRequest | None = None,
    user_id: str = Depends(require_user_id),
):
    """Start a new voice agent conversation session."""
    try:
        logger.info(f"[VoiceAgentRoutes] Starting conversation for user: {user_id}")

        onboarding = bool(body.onboarding_mode) if body else False
        landing = bool(body.landing_onboarding) if body else False
        result = voice_agent_service.start_conversation(
            user_id=user_id,
            db=create_database_client(),
            idea_id=body.idea_id if body else None,
            onboarding_mode=onboarding,
            landing_onboarding=landing,
        )
        return result

    except Exception as e:
        logger.error(f"[VoiceAgentRoutes] Error starting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/process", response_model=ProcessMessageResponse)
def process_message(body: ProcessMessageRequest, user_id: str = Depends(require_user_id)):
    """Process a user message and generate AI response."""
    try:
        logger.info(f"[VoiceAgentRoutes] Processing message for user: {user_id}")

        messages = [{"role": m.role, "content": m.content} for m in body.messages]
        result = voice_agent_service.process_message(
            conversation_messages=messages,
            user_message=body.user_message,
            user_id=user_id,
            db=create_database_client(),
            idea_id=body.idea_id,
            onboarding_mode=bool(body.onboarding_mode),
            landing_onboarding=bool(body.landing_onboarding),
        )

        return ProcessMessageResponse(
            response=VoiceAgentResponse(**result["response"]), messages=result["messages"]
        )

    except Exception as e:
        logger.error(f"[VoiceAgentRoutes] Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@router.post("/process-stream")
async def process_message_stream(
    body: ProcessMessageRequest, user_id: str = Depends(require_user_id)
):
    """Process a user message and stream the spoken reply before structured enrichment."""
    logger.info(f"[VoiceAgentRoutes] Streaming message for user: {user_id}")

    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    db = create_database_client()

    def event_stream() -> Generator[str, None, None]:
        try:
            prepared = voice_agent_service._prepare_turn(
                conversation_messages=messages,
                user_message=body.user_message,
                user_id=user_id,
                db=db,
                idea_id=body.idea_id,
                onboarding_mode=bool(body.onboarding_mode),
                landing_onboarding=bool(body.landing_onboarding),
            )
            cleaned_user_message = prepared["cleaned_user_message"]
            context = prepared["context"]
            normalized_history = prepared["normalized_history"]

            if not cleaned_user_message:
                response = voice_agent_service._error_response(
                    "I didn't catch anything usable there. Give me the idea again in one sentence."
                )
                yield _sse_event("structured", {"response": response, "messages": messages})
                yield _sse_event("done", {"ok": True})
                return

            if context.get("landing_onboarding"):
                landing_response = voice_agent_service._process_landing_onboarding_turn(
                    conversation_messages=messages,
                    user_message=cleaned_user_message,
                    context=context,
                    normalized_history=normalized_history,
                )
                updated_messages = list(messages)
                updated_messages.append({"role": "user", "content": cleaned_user_message})
                updated_messages.append(
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            voice_agent_service._assistant_history_payload(landing_response)
                        ),
                    }
                )
                yield _sse_event("delta", {"text": landing_response["message"]})
                yield _sse_event(
                    "structured", {"response": landing_response, "messages": updated_messages}
                )
                yield _sse_event("done", {"ok": True})
                return

            if voice_agent_service._looks_like_operational_message(cleaned_user_message):
                response = voice_agent_service._operational_redirect_response(context)
                updated_messages = list(messages)
                updated_messages.append({"role": "user", "content": cleaned_user_message})
                updated_messages.append(
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            voice_agent_service._assistant_history_payload(response)
                        ),
                    }
                )
                yield _sse_event("delta", {"text": response["message"]})
                yield _sse_event("structured", {"response": response, "messages": updated_messages})
                yield _sse_event("done", {"ok": True})
                return

            if not voice_agent_service.router.is_available():
                response = voice_agent_service._fallback_structured_response(
                    context,
                    normalized_history,
                    cleaned_user_message,
                )
                updated_messages = list(messages)
                updated_messages.append({"role": "user", "content": cleaned_user_message})
                updated_messages.append(
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            voice_agent_service._assistant_history_payload(response)
                        ),
                    }
                )
                yield _sse_event("delta", {"text": response["message"]})
                yield _sse_event("structured", {"response": response, "messages": updated_messages})
                yield _sse_event("done", {"ok": True})
                return

            spoken_chunks: list[str] = []
            for chunk in voice_agent_service.stream_spoken_turn(
                context=context,
                normalized_history=normalized_history,
                latest_user_message=cleaned_user_message,
            ):
                spoken_chunks.append(chunk)
                yield _sse_event("delta", {"text": chunk})

            spoken_message = "".join(spoken_chunks)
            response = voice_agent_service.enrich_structured_turn(
                context=context,
                normalized_history=normalized_history,
                user_message=cleaned_user_message,
                assistant_message=spoken_message,
            )
            updated_messages = list(messages)
            updated_messages.append({"role": "user", "content": cleaned_user_message})
            updated_messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(voice_agent_service._assistant_history_payload(response)),
                }
            )
            yield _sse_event("structured", {"response": response, "messages": updated_messages})
            yield _sse_event("done", {"ok": True})
        except Exception as exc:
            logger.error("[VoiceAgentRoutes] Stream processing error: %s", exc)
            yield _sse_event(
                "error", {"error": "Voice mode could not process that turn. Try again."}
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/qualify", response_model=QualifyIdeaResponse)
def qualify_idea(body: QualifyIdeaRequest, user_id: str = Depends(require_user_id)):
    """Extract and qualify the idea from a conversation."""
    try:
        logger.info(f"[VoiceAgentRoutes] Qualifying idea for user: {user_id}")

        messages = [{"role": m.role, "content": m.content} for m in body.messages]
        result = voice_agent_service.qualify_idea(
            conversation_messages=messages,
            user_id=user_id,
            db=create_database_client(),
            idea_id=body.idea_id,
        )

        return QualifyIdeaResponse(**result)

    except Exception as e:
        logger.error(f"[VoiceAgentRoutes] Error qualifying idea: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


class TTSRequest(BaseModel):
    text: str
    voice: str | None = None
    model: str | None = None
    instructions: str | None = None


class TTSResponse(BaseModel):
    audio_base64: str | None = None
    success: bool
    fallback_to_browser: bool = False


class TranscribeRequest(BaseModel):
    audio_base64: str
    mime_type: str | None = None
    filename: str | None = None
    language: str | None = None


class TranscribeResponse(BaseModel):
    success: bool
    transcript: str | None = None
    error: str | None = None


@router.post("/tts", response_model=TTSResponse)
def text_to_speech(body: TTSRequest, user_id: str = Depends(require_user_id)):
    """Convert text to speech using OpenAI TTS API."""
    try:
        logger.info(f"[VoiceAgentRoutes] TTS request for user: {user_id}")

        if not tts_service.is_available():
            return TTSResponse(audio_base64=None, success=False, fallback_to_browser=True)

        audio_base64 = tts_service.text_to_speech_base64(
            body.text,
            body.voice,
            body.model,
            body.instructions,
        )

        if audio_base64:
            return TTSResponse(audio_base64=audio_base64, success=True, fallback_to_browser=False)
        else:
            return TTSResponse(audio_base64=None, success=False, fallback_to_browser=True)

    except Exception as e:
        logger.error(f"[VoiceAgentRoutes] TTS error: {e}")
        return TTSResponse(audio_base64=None, success=False, fallback_to_browser=True)


@router.post("/transcribe", response_model=TranscribeResponse)
def transcribe_audio(body: TranscribeRequest, user_id: str = Depends(require_user_id)):
    """Transcribe a short browser-recorded microphone clip."""
    try:
        logger.info(f"[VoiceAgentRoutes] Transcribe request for user: {user_id}")

        if not stt_service.is_available():
            return TranscribeResponse(
                success=False,
                transcript=None,
                error="Voice transcription is unavailable right now.",
            )

        transcript = stt_service.transcribe_base64(
            body.audio_base64,
            filename=body.filename,
            mime_type=body.mime_type,
            language=body.language,
        )

        if transcript:
            return TranscribeResponse(success=True, transcript=transcript, error=None)

        return TranscribeResponse(
            success=False,
            transcript=None,
            error="Manifest Voice could not transcribe that recording.",
        )
    except Exception as e:
        logger.error(f"[VoiceAgentRoutes] Transcription error: {e}")
        return TranscribeResponse(
            success=False,
            transcript=None,
            error="Manifest Voice could not transcribe that recording.",
        )
