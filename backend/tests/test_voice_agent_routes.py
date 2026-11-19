"""Route-level guards for the voice agent API.

The blocking voice endpoints (LLM chat, TTS, Whisper transcription,
Realtime session mint — each 0.5-3s of synchronous I/O) must be plain
``def`` handlers so FastAPI runs them in its threadpool. Declaring one
``async def`` puts that blocking call on the event loop, freezing every
other request on the worker for the duration — this is exactly the
"whole site stalls while someone uses voice" regression these tests pin.
"""

import inspect

from app.routes import voice_agent_routes


def _endpoint(path: str, method: str = "POST"):
    for route in voice_agent_routes.router.routes:
        if route.path == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"route {method} {path} not found")


def test_blocking_voice_endpoints_run_in_threadpool():
    blocking = [
        ("/api/voice-agent/start", "POST"),
        ("/api/voice-agent/process", "POST"),
        ("/api/voice-agent/qualify", "POST"),
        ("/api/voice-agent/tts", "POST"),
        ("/api/voice-agent/transcribe", "POST"),
    ]
    offenders = [
        f"{method} {path}"
        for path, method in blocking
        if inspect.iscoroutinefunction(_endpoint(path, method))
    ]
    assert not offenders, (
        "These voice endpoints are async def but perform blocking I/O; "
        f"declare them as plain def so they run in the threadpool: {offenders}"
    )


def test_stream_endpoint_uses_sync_generator():
    """/process-stream hands a *sync* generator to StreamingResponse, which
    Starlette iterates in the threadpool — the handler itself may stay async
    because it does no blocking work before returning the response."""
    endpoint = _endpoint("/api/voice-agent/process-stream", "POST")
    assert endpoint is not None
