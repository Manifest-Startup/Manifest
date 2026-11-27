"""End to end: real Pipecat pipeline, spoken question in, tool call as the person, speech out.

OpenAI (STT, chat, TTS) and Manifest's GraphQL are replaced by one local stub, so the test
needs no key and no network. The question is a recorded WAV (macOS `say`, 16 kHz mono).
"""

from __future__ import annotations

import asyncio
import json
import math
import socket
import struct
import threading
import time
import wave
from pathlib import Path

import pytest

pytest.importorskip("pipecat")
import pipecat.frames.protobufs.frames_pb2 as fp  # noqa: E402
import uvicorn  # noqa: E402
import websockets  # noqa: E402
from app.routes import voice_live_routes  # noqa: E402
from fastapi import FastAPI, Request, WebSocket  # noqa: E402
from fastapi.responses import JSONResponse, Response, StreamingResponse  # noqa: E402

WAV = Path(__file__).parent / "fixtures" / "voice" / "what-ideas-do-i-have.wav"


def add_realtime_stt(app: FastAPI, log: list[dict], transcript: str, deltas: list[str]) -> None:
    """OpenAI's realtime transcription socket with server VAD, as Pipecat drives it.

    After ~0.6 s of audio it hears speech start, after ~1.2 s it streams the deltas, hears
    the pause and sends the final transcript, the way the real service does once per turn.
    """

    @app.websocket("/v1/realtime")
    async def realtime(ws: WebSocket):
        await ws.accept()
        log.append({"realtime_auth": ws.headers.get("authorization")})
        await ws.send_json({"type": "session.created"})
        appended = 0
        try:
            while True:
                event = json.loads(await ws.receive_text())
                kind = event.get("type")
                if kind == "session.update":
                    log.append(
                        {"turn_detection": event["session"]["audio"]["input"].get("turn_detection")}
                    )
                    await ws.send_json({"type": "session.updated"})
                elif kind == "input_audio_buffer.append":
                    appended += 1
                    if appended == 30:
                        await ws.send_json({"type": "input_audio_buffer.speech_started"})
                    elif appended == 60:
                        for delta in deltas:
                            await ws.send_json(
                                {
                                    "type": "conversation.item.input_audio_transcription.delta",
                                    "delta": delta,
                                }
                            )
                        await ws.send_json({"type": "input_audio_buffer.speech_stopped"})
                        await ws.send_json({"type": "input_audio_buffer.committed"})
                        await ws.send_json(
                            {
                                "type": "conversation.item.input_audio_transcription.completed",
                                "transcript": transcript,
                            }
                        )
        except Exception:
            return


def _stub() -> tuple[FastAPI, list[dict]]:
    app, log = FastAPI(), []
    add_realtime_stt(app, log, "What ideas do I have?", ["What ideas ", "do I have?"])

    def chunk(delta: dict, finish: str | None = None) -> str:
        body = {
            "id": "c",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "stub",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(body)}\n\n"

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        messages = body["messages"]
        log.append({"llm_tools": len(body.get("tools") or [])})

        def stream():
            if messages[-1].get("role") == "tool":
                yield chunk(
                    {"role": "assistant", "content": "You have one idea, Solar Cold Chain."}
                )
                yield chunk({}, "stop")
            elif any(m.get("role") == "user" for m in messages):
                call = {
                    "index": 0,
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "ideas", "arguments": '{"first": 5}'},
                }
                yield chunk({"role": "assistant", "tool_calls": [call]})
                yield chunk({}, "tool_calls")
            else:
                log.append({"llm_without_user": True})
                yield chunk({"role": "assistant", "content": "?"})
                yield chunk({}, "stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/v1/audio/speech")
    async def speech(request: Request):
        log.append({"tts": (await request.json()).get("input")})
        pcm = b"".join(
            struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / 24000)))
            for i in range(4800)
        )
        return Response(pcm, media_type="audio/pcm")

    @app.post("/graphql")
    async def graphql(request: Request):
        log.append({"auth": request.headers.get("authorization"), "body": await request.json()})
        return JSONResponse(
            {"data": {"ideas": {"edges": [{"node": {"title": "Solar Cold Chain"}}]}}}
        )

    return app, log


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(app: FastAPI, port: int) -> uvicorn.Server:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    # Both servers must accept connections before the call starts: the greeting is spoken the
    # moment the socket opens, so a late stub would silently drop it (seen on a loaded machine).
    deadline = time.time() + 60
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, f"test server on port {port} didn't start"
    return server


def _frame_audio(pcm: bytes) -> bytes:
    return fp.Frame(
        audio=fp.AudioRawFrame(audio=pcm, sample_rate=16000, num_channels=1)
    ).SerializeToString()


async def _talk(url: str) -> tuple[list, int]:
    with wave.open(str(WAV)) as w:
        speech = w.readframes(w.getnframes())
    silence = b"\x00\x00" * 320
    events: list = []
    audio = 0
    ready = json.dumps(
        {"label": "rtvi-ai", "type": "client-ready", "id": "1", "data": {"version": "2.3.0"}}
    )
    async with websockets.connect(
        url, additional_headers={"Authorization": "Bearer tok"}, open_timeout=60
    ) as ws:
        await ws.send(fp.Frame(message=fp.MessageFrame(data=ready)).SerializeToString())

        async def read():
            nonlocal audio
            async for raw in ws:
                frame = fp.Frame.FromString(raw)
                if frame.WhichOneof("frame") == "audio":
                    audio += len(frame.audio.audio)
                elif frame.WhichOneof("frame") == "message":
                    data = json.loads(frame.message.data)
                    events.append((data.get("type"), data.get("data")))

        reader = asyncio.create_task(read())
        # Like a person, let the hello finish before talking: speaking over it interrupts (and
        # cancels) the greeting, which on a busy machine is still being synthesised.
        # No audio meanwhile: the stub recogniser counts audio chunks, not loudness, so even
        # silence would start a "turn" and cut the greeting off.
        deadline = time.time() + 30
        while time.time() < deadline and "bot-stopped-speaking" not in [t for t, _ in events]:
            await asyncio.sleep(0.02)
        for _ in range(25):
            await ws.send(_frame_audio(silence))
            await asyncio.sleep(0.02)
        for i in range(0, len(speech), 640):
            await ws.send(_frame_audio(speech[i : i + 640]))
            await asyncio.sleep(0.02)
        deadline = time.time() + 12
        while time.time() < deadline:
            await ws.send(_frame_audio(silence))
            await asyncio.sleep(0.02)
            spoken = [d for t, d in events if t == "bot-output"]
            if any("Solar Cold Chain" in str(d) for d in spoken):
                await asyncio.sleep(0.5)
                break
        reader.cancel()
    return events, audio


def test_spoken_question_runs_a_tool_and_answers_out_loud(monkeypatch):
    stub, log = _stub()
    stub_port, voice_port = _free_port(), _free_port()
    monkeypatch.setenv("VOICE_OPENAI_BASE_URL", f"http://127.0.0.1:{stub_port}/v1")
    monkeypatch.setenv("VOICE_API_ORIGIN", f"http://127.0.0.1:{stub_port}")
    monkeypatch.delenv("EDGE_SHARED_SECRET", raising=False)
    monkeypatch.setattr(voice_live_routes, "get_current_user_id_optional", lambda ws: "user-1")
    monkeypatch.setattr(voice_live_routes, "_key_for", lambda user_id: "sk-stub")
    monkeypatch.setattr(voice_live_routes, "_first_name", lambda user_id: "Ada")
    voice_app = FastAPI()
    voice_app.include_router(voice_live_routes.router)
    servers = [_serve(stub, stub_port), _serve(voice_app, voice_port)]
    try:
        events, audio = asyncio.run(
            _talk(f"ws://127.0.0.1:{voice_port}/api/voice-agent/live?path=/ideas")
        )
    finally:
        for server in servers:
            server.should_exit = True

    types = [t for t, _ in events]
    assert "bot-ready" in types
    transcripts = [d.get("text") for t, d in events if t == "user-transcription"]
    assert "What ideas do I have?" in transcripts
    tools = [d for t, d in events if t == "server-message" and d.get("type") == "manifest.tool"]
    assert [(d["name"], d["phase"]) for d in tools] == [("ideas", "started"), ("ideas", "finished")]
    graphql = [entry for entry in log if "auth" in entry]
    assert graphql and graphql[0]["auth"] == "Bearer tok"
    assert graphql[0]["body"]["variables"] == {"first": 5}
    assert any(entry.get("tts") == "You have one idea, Solar Cold Chain." for entry in log)
    assert audio > 0
    # Speed: the greeting is spoken without a model call, and OpenAI ends the turn.
    assert any(entry.get("tts") == "Hi, Ada. What are we working on?" for entry in log)
    assert not any("llm_without_user" in entry for entry in log)
    assert any((entry.get("turn_detection") or {}).get("type") == "server_vad" for entry in log)
    assert all(entry["llm_tools"] < 29 for entry in log if "llm_tools" in entry)
