"""Relay and dictation modes, end to end on a real Pipecat pipeline with local stubs.

Relay: the person's own agent answers on the client; the server only hears and speaks.
Dictation: speech to text only, streamed (deltas, then the final sentence) for the note.
"""

from __future__ import annotations

import asyncio
import json
import math
import struct
import time
import wave

import pytest

pytest.importorskip("pipecat")
import pipecat.frames.protobufs.frames_pb2 as fp  # noqa: E402
import websockets  # noqa: E402
from app.routes import voice_live_routes  # noqa: E402
from app.services.voice.live.relay import clean_say, last_user_text  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402
from test_voice_live_pipeline import WAV, _frame_audio, _free_port, _serve, add_realtime_stt  # noqa: E402


def _message(kind: str, data: dict | None = None) -> bytes:
    body = json.dumps({"label": "rtvi-ai", "type": kind, "id": kind[:6], "data": data or {}})
    return fp.Frame(message=fp.MessageFrame(data=body)).SerializeToString()


def _openai_stub() -> tuple[FastAPI, list[dict]]:
    app, log = FastAPI(), []

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        log.append({"llm": True})  # relay must never call a model
        return JSONResponse({}, status_code=500)

    @app.post("/v1/audio/speech")
    async def speech(request: Request):
        log.append({"tts": (await request.json()).get("input")})
        pcm = b"".join(
            struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / 24000)))
            for i in range(4800)
        )
        return Response(pcm, media_type="audio/pcm")

    add_realtime_stt(app, log, "Solar cold chain.", ["Solar ", "cold ", "chain"])

    return app, log


def _start(monkeypatch) -> tuple[int, list[dict], list]:
    stub, log = _openai_stub()
    stub_port, voice_port = _free_port(), _free_port()
    monkeypatch.setenv("VOICE_OPENAI_BASE_URL", f"http://127.0.0.1:{stub_port}/v1")
    monkeypatch.delenv("EDGE_SHARED_SECRET", raising=False)
    monkeypatch.setattr(voice_live_routes, "get_current_user_id_optional", lambda ws: "user-1")
    monkeypatch.setattr(voice_live_routes, "_key_for", lambda user_id: "sk-stub")
    voice_app = FastAPI()
    voice_app.include_router(voice_live_routes.router)
    servers = [_serve(stub, stub_port), _serve(voice_app, voice_port)]
    return voice_port, log, servers


async def _session(url: str, *, until, on_event=None) -> list:
    with wave.open(str(WAV)) as w:
        speech = w.readframes(w.getnframes())
    silence = b"\x00\x00" * 320
    events: list = []
    async with websockets.connect(url, additional_headers={"Authorization": "Bearer tok"}) as ws:
        await ws.send(_message("client-ready", {"version": "2.3.0"}))

        async def read():
            async for raw in ws:
                frame = fp.Frame.FromString(raw)
                if frame.WhichOneof("frame") == "message":
                    data = json.loads(frame.message.data)
                    events.append((data.get("type"), data.get("data")))
                    if on_event:
                        await on_event(ws, data.get("type"), data.get("data") or {})

        reader = asyncio.create_task(read())
        for _ in range(25):
            await ws.send(_frame_audio(silence))
            await asyncio.sleep(0.02)
        for i in range(0, len(speech), 640):
            await ws.send(_frame_audio(speech[i : i + 640]))
            await asyncio.sleep(0.02)
        deadline = time.time() + 12
        while time.time() < deadline and not until(events):
            await ws.send(_frame_audio(silence))
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.3)
        reader.cancel()
    return events


def test_relay_hands_the_turn_to_the_persons_agent_and_speaks_its_reply(monkeypatch):
    port, log, servers = _start(monkeypatch)

    async def agent(ws, kind, data):
        if kind == "server-message" and data.get("type") == "manifest.turn":
            await ws.send(
                _message(
                    "client-message",
                    {"t": "manifest.say", "d": {"text": f"Claude heard: {data['text']}"}},
                )
            )

    try:
        events = asyncio.run(
            _session(
                f"ws://127.0.0.1:{port}/api/voice-agent/live?mode=relay",
                until=lambda _e: any("Claude heard" in str(e.get("tts")) for e in log),
                on_event=agent,
            )
        )
    finally:
        for server in servers:
            server.should_exit = True

    turns = [d for t, d in events if t == "server-message" and d.get("type") == "manifest.turn"]
    assert turns and turns[0]["text"] == "Solar cold chain."
    assert any(e.get("tts") == "Claude heard: Solar cold chain." for e in log)
    assert not any("llm" in e for e in log)


def test_dictation_streams_words_then_the_final_sentence(monkeypatch):
    port, log, servers = _start(monkeypatch)

    def finished(events):
        return any(t == "user-transcription" and d.get("final") for t, d in events)

    try:
        events = asyncio.run(
            _session(f"ws://127.0.0.1:{port}/api/voice-agent/live?mode=dictate", until=finished)
        )
    finally:
        for server in servers:
            server.should_exit = True

    words = [d for t, d in events if t == "user-transcription"]
    assert [d["text"] for d in words if not d.get("final")] == ["Solar ", "cold ", "chain"]
    assert [d["text"] for d in words if d.get("final")] == ["Solar cold chain."]
    assert {"realtime_auth": "Bearer sk-stub"} in log
    assert not any("tts" in e or "llm" in e for e in log)


def test_unknown_mode_is_refused():
    assert voice_live_routes.voice_mode(None) == "agent"
    assert voice_live_routes.voice_mode("Relay") == "relay"
    assert voice_live_routes.voice_mode("dictate") == "dictate"
    assert voice_live_routes.voice_mode("root") is None


def test_relay_helpers():
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ok"},
        {
            "role": "user",
            "content": [{"type": "text", "text": "open"}, {"type": "text", "text": "it"}],
        },
    ]
    assert last_user_text(messages) == "open it"
    assert last_user_text([]) == ""
    assert clean_say({"text": "  hi\n there "}) == "hi there"
    assert clean_say("nope") == ""
    assert len(clean_say({"text": "a" * 9000})) == 4000


def test_completed_transcripts_end_the_turn_without_waiting(monkeypatch):
    """OpenAI's completed transcript is final; unmarked, Pipecat waited 0.5 s every turn."""
    from app.services.voice.live.bot import VoiceSettings, build_stt
    from pipecat.frames.frames import TranscriptionFrame
    from pipecat.services.openai.stt import OpenAIRealtimeSTTService

    pushed = []

    async def capture(self, frame, direction=None):
        pushed.append(frame)

    monkeypatch.setattr(OpenAIRealtimeSTTService, "push_frame", capture)
    stt = build_stt("sk-test", VoiceSettings())
    asyncio.run(stt.push_frame(TranscriptionFrame("Hello there.", "user", "now")))
    assert pushed and pushed[0].finalized is True
