"""Dictation mode: speech to text only, streamed as it is spoken, for writing into a note.

    mic ─▶ OpenAI Realtime transcription (server VAD) ─▶ RTVI user-transcription

No model and no speech out: the person's words arrive as ``user-transcription`` events,
``final: false`` for each new piece (a delta to append) and ``final: true`` with the whole
segment once they pause. The web app writes them into the note at the cursor.
"""

from __future__ import annotations

from typing import Any

from app.services.voice.live.bot import VoiceSettings, build_stt, build_transport, run_worker

DICTATION_IDLE_SECONDS = 2 * 60


async def run_dictation_session(
    websocket: Any, *, openai_key: str, settings: VoiceSettings | None = None
) -> None:
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker

    settings = settings or VoiceSettings.from_env()
    transport = build_transport(websocket, audio_out=False)
    pipeline = Pipeline([transport.input(), build_stt(openai_key, settings), transport.output()])
    worker = PipelineWorker(
        pipeline, params=PipelineParams(), idle_timeout_secs=DICTATION_IDLE_SECONDS
    )

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport: Any, _client: Any) -> None:
        await worker.cancel()

    await run_worker(worker)
