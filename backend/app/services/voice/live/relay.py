"""Relay mode: the person's own agent is the brain, Manifest is the voice.

    mic ─▶ streaming STT + turn ─▶ RelayBrain ══ manifest.turn ══▶ client
                                                    (Claude Code, Codex, any command)
    speaker ◀─ TTS ◀─ RelayBrain ◀══ manifest.say ══ client

The server keeps doing what it is good at (turn detection, interruptions, speech in and
out on the person's own OpenAI key) and hands each finished turn to the client as text.
The client runs whatever agent the person already uses, with that agent's own tools,
permissions and session history, and sends its reply back to be spoken. The relay never
runs tools or a model of its own, so it cannot do anything the person's agent would not.

Server → client (RTVI server-message):
    manifest.turn  {id, text}           what the person just said; answer it
Client → server (RTVI client-message):
    manifest.say   {text, id?}          speak this (send sentences as they arrive)
    manifest.hush  {}                   stop speaking now
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.services.voice.live.bot import (
    IDLE_LIMIT_SECONDS,
    VoiceSettings,
    build_stt,
    build_transport,
    build_tts,
    run_worker,
)

MAX_SAY_CHARS = 4000


def last_user_text(messages: list[Any]) -> str:
    """The newest user message in an LLM context, as plain text."""
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and part.get("type") in (None, "text")
            ]
            return " ".join(p for p in parts if p).strip()
        return ""
    return ""


def clean_say(data: Any) -> str:
    text = str((data or {}).get("text") or "") if isinstance(data, dict) else ""
    return " ".join(text.split())[:MAX_SAY_CHARS]


def relay_brain_class() -> type:
    """Built lazily so the API process only imports Pipecat when voice is used."""
    from pipecat.frames.frames import LLMContextFrame, TTSSpeakFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class RelayBrain(FrameProcessor):
        """Stands where the LLM would: turns go out to the client, replies come back."""

        def __init__(self, notify: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
            super().__init__()
            self._notify = notify
            self.turns = 0

        async def process_frame(self, frame: Any, direction: Any) -> None:
            await super().process_frame(frame, direction)
            if isinstance(frame, LLMContextFrame):
                text = last_user_text(list(frame.context.get_messages()))
                if text:
                    self.turns += 1
                    await self._notify(
                        {"type": "manifest.turn", "id": str(self.turns), "text": text}
                    )
                return  # the person's agent answers, not a model here
            await self.push_frame(frame, direction)

        async def say(self, text: str) -> None:
            if text:
                await self.push_frame(TTSSpeakFrame(text), FrameDirection.DOWNSTREAM)

    return RelayBrain


async def run_relay_session(
    websocket: Any, *, openai_key: str, settings: VoiceSettings | None = None
) -> None:
    """Listen and speak for an agent that runs on the client."""
    from pipecat.frames.frames import InterruptionFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
    )

    settings = settings or VoiceSettings.from_env()
    transport = build_transport(websocket)
    worker_ref: dict[str, Any] = {}

    async def notify(data: dict[str, Any]) -> None:
        worker = worker_ref.get("worker")
        if worker is not None:
            await worker.rtvi.send_server_message(data)

    brain = relay_brain_class()(notify)
    user_aggregator, _assistant = LLMContextAggregatorPair(
        LLMContext(), user_params=LLMUserAggregatorParams()
    )
    pipeline = Pipeline(
        [
            transport.input(),
            build_stt(openai_key, settings),
            user_aggregator,
            brain,
            build_tts(openai_key, settings),
            transport.output(),
        ]
    )
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        # A coding agent can think for minutes; the session limit still applies.
        idle_timeout_secs=IDLE_LIMIT_SECONDS * 3,
    )
    worker_ref["worker"] = worker

    @worker.rtvi.event_handler("on_client_message")
    async def on_client_message(_rtvi: Any, message: Any) -> None:
        kind = getattr(message, "type", None)
        if kind == "manifest.say":
            await brain.say(clean_say(getattr(message, "data", None)))
        elif kind == "manifest.hush":
            await worker.queue_frames([InterruptionFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport: Any, _client: Any) -> None:
        await worker.cancel()

    await run_worker(worker)
