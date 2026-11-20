"""Live voice (Pipecat) routes: one WebSocket per conversation, plus a cheap status probe.

``GET  /api/voice-agent/live/status``  can this person talk to Manifest right now?
``WS   /api/voice-agent/live``         the conversation (RTVI over protobuf frames)
    ``?mode=agent``    (default) Manifest's own agent with every Manifest tool
    ``?mode=relay``    the person's own agent (Claude Code, Codex, …) answers on the client
    ``?mode=dictate``  speech to text only, streamed, for writing into a note

Browsers authenticate with the session cookie and must come from a Manifest origin
(cross-site WebSocket hijacking would otherwise ride the cookie). The CLI and other
agents send ``Authorization: Bearer <session token>``. See docs/VOICE_AGENT_API.md.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import Any
from urllib.parse import urlsplit

from app.auth.current_user import get_current_user_id_optional, require_user_id
from app.security.config import frontend_origins_from_env, is_production_environment
from app.services.ai.credentials import MISSING_KEY_MESSAGE
from app.services.ai.user_keys import load_user_key
from app.utils.logger import logger
from fastapi import APIRouter, Depends, WebSocket
from pydantic import BaseModel

router = APIRouter(prefix="/api/voice-agent", tags=["voice-agent"])

# WebSocket close codes (4000-4999 are application-defined).
CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN_ORIGIN = 4403
CLOSE_NO_KEY = 4402
CLOSE_UNAVAILABLE = 4503

VOICE_MODES = ("agent", "relay", "dictate")


def voice_mode(value: str | None) -> str | None:
    """The requested mode, or None when it is not one we serve."""
    mode = (value or "agent").strip().lower()
    return mode if mode in VOICE_MODES else None


class LiveVoiceStatus(BaseModel):
    available: bool
    reason: str | None = None
    message: str | None = None
    transport: str = "websocket"
    protocol: str = "rtvi"


def pipecat_installed() -> bool:
    try:
        import pipecat  # noqa: F401
    except Exception:
        return False
    return True


def _key_for(user_id: str) -> str | None:
    try:
        return load_user_key(str(user_id))
    except Exception as exc:  # a broken key row must not take voice down with a 500
        logger.warning("[voice.live] key lookup failed: %s", type(exc).__name__)
        return None


def live_status(user_id: str) -> LiveVoiceStatus:
    if not pipecat_installed():
        return LiveVoiceStatus(
            available=False, reason="unavailable", message="Voice isn't installed on this server."
        )
    if not _key_for(user_id):
        return LiveVoiceStatus(available=False, reason="no_api_key", message=MISSING_KEY_MESSAGE)
    return LiveVoiceStatus(available=True)


@router.get("/live/status", response_model=LiveVoiceStatus)
def live_voice_status(user_id: str = Depends(require_user_id)) -> LiveVoiceStatus:
    """Whether live voice can start for this person (never mints or returns a credential).

    The app asks as voice opens, so this is also when Pipecat starts loading.
    """
    status = live_status(user_id)
    if status.available:
        from app.services.voice.live.bot import warm_up

        warm_up()
    return status


def _session_token(websocket: WebSocket) -> tuple[str | None, bool]:
    """(token, came_from_cookie)."""
    for name in ("session_token", "access_token"):
        token = websocket.cookies.get(name)
        if token:
            return token, True
    header = websocket.headers.get("authorization") or ""
    if header.startswith("Bearer "):
        return header.removeprefix("Bearer ").strip() or None, False
    return None, False


def origin_allowed(origin: str | None, host: str | None) -> bool:
    """Same-origin, a configured frontend origin, or localhost outside production."""
    if not origin:
        return False
    parsed = urlsplit(origin)
    if not parsed.scheme or not parsed.netloc:
        return False
    if host and parsed.netloc == host:
        return True
    allowed = set(frontend_origins_from_env())
    app_base = (os.getenv("APP_BASE_URL") or "").strip().rstrip("/")
    if app_base:
        allowed.add(app_base)
    if origin.rstrip("/") in allowed:
        return True
    return not is_production_environment() and parsed.hostname in {"localhost", "127.0.0.1"}


def _api_origin() -> str:
    configured = (os.getenv("VOICE_API_ORIGIN") or "").strip().rstrip("/")
    return configured or f"http://127.0.0.1:{os.getenv('PORT') or '8000'}"


def _first_name(user_id: str) -> str | None:
    try:
        from app.db.database import create_database_client

        rows = (
            create_database_client()
            .table("users")
            .select("first_name")
            .eq("id", user_id)
            .limit(1)
            .execute()
            .data
        )
        return (rows[0].get("first_name") or None) if rows else None
    except Exception:
        return None


def _client_ip(websocket: WebSocket) -> str | None:
    forwarded = websocket.headers.get("cf-connecting-ip")
    if forwarded:
        return forwarded
    return websocket.client.host if websocket.client else None


async def _reject(websocket: WebSocket, code: int, reason: str) -> None:
    """Accept, explain, then close with an application code.

    A close before accept reaches browsers as an HTTP 403 (code 1006), and some proxies drop
    close codes, so the reason also goes out first as an RTVI ``error`` message that Pipecat
    clients read ("… (Code: 4402)").
    """
    await websocket.accept()
    with contextlib.suppress(Exception):
        await websocket.send_bytes(rtvi_error_frame(code, reason))
    await websocket.close(code=code, reason=reason)


def rtvi_error_frame(code: int, reason: str) -> bytes:
    """A protobuf ``Frame{message}`` carrying an RTVI fatal error (empty without Pipecat)."""
    try:
        import pipecat.frames.protobufs.frames_pb2 as frames
    except Exception:
        return b""
    text = f"{reason} (Code: {code})"
    payload = {
        "label": "rtvi-ai",
        "type": "error",
        "data": {"error": text, "message": text, "fatal": True, "code": code},
    }
    return frames.Frame(message=frames.MessageFrame(data=json.dumps(payload))).SerializeToString()


@router.websocket("/live")
async def live_voice(websocket: WebSocket) -> None:
    """One live voice conversation with the Manifest agent."""
    from starlette.concurrency import run_in_threadpool

    token, from_cookie = _session_token(websocket)
    if from_cookie and not origin_allowed(
        websocket.headers.get("origin"), websocket.headers.get("host")
    ):
        await _reject(websocket, CLOSE_FORBIDDEN_ORIGIN, "Origin not allowed")
        return
    # Session checks hit the database; keep them off the event loop.
    user_id = await run_in_threadpool(get_current_user_id_optional, websocket)  # type: ignore[arg-type]
    if not token or not user_id:
        await _reject(websocket, CLOSE_UNAUTHENTICATED, "Sign in to talk to Manifest")
        return
    if not pipecat_installed():
        await _reject(websocket, CLOSE_UNAVAILABLE, "Voice isn't installed on this server")
        return
    openai_key = await run_in_threadpool(_key_for, str(user_id))
    if not openai_key:
        await _reject(websocket, CLOSE_NO_KEY, "Add your OpenAI key in Account → AI settings")
        return

    params: dict[str, Any] = dict(websocket.query_params)
    mode = voice_mode(params.get("mode"))
    if mode is None:
        await _reject(websocket, CLOSE_UNAVAILABLE, "Unknown voice mode")
        return
    if mode != "agent":
        await websocket.accept()
        logger.info(
            "[voice.live] session started", extra={"enduser.id": str(user_id), "voice.mode": mode}
        )
        try:
            if mode == "relay":
                from app.services.voice.live.relay import run_relay_session

                await run_relay_session(websocket, openai_key=openai_key)
            else:
                from app.services.voice.live.dictation import run_dictation_session

                await run_dictation_session(websocket, openai_key=openai_key)
        finally:
            logger.info(
                "[voice.live] session ended", extra={"enduser.id": str(user_id), "voice.mode": mode}
            )
        return

    from app.services.voice.live.bot import VoiceSessionContext, run_voice_session
    from app.services.voice.live.tools import ToolExecutor

    session = VoiceSessionContext(
        first_name=await run_in_threadpool(_first_name, str(user_id)),
        path=(params.get("path") or "")[:200] or None,
        idea_id=(params.get("idea_id") or "")[:80] or None,
        idea_title=(params.get("idea_title") or "")[:200] or None,
    )
    executor = ToolExecutor(
        api_origin=_api_origin(), session_token=token, client_ip=_client_ip(websocket)
    )
    await websocket.accept()
    logger.info("[voice.live] session started", extra={"enduser.id": str(user_id)})
    try:
        await run_voice_session(
            websocket, openai_key=openai_key, executor=executor, session=session
        )
    finally:
        logger.info("[voice.live] session ended", extra={"enduser.id": str(user_id)})
