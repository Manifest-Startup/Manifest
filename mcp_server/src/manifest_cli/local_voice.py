"""Natural voice on this computer, with the person's own agent as the brain. No API key.

    Manifest app (Pipecat client) ══ ws://127.0.0.1:47822 (RTVI, protobuf) ══▶
        Silero VAD + smart turn ─▶ Whisper (MLX, Apple silicon) ─▶ AgentBrain ─▶ Kokoro ─▶ speaker
                                                       Claude Code / Codex

The same Pipecat pipeline shape and client protocol as Manifest's server voice, but every
model runs locally: Whisper hears, Kokoro speaks in a natural neural voice, and the agent
the person already uses answers, streaming sentence by sentence so speech starts early.
People can interrupt it at any time. Only Manifest's pages may connect (Origin check).

Extra: ``pip install 'manifest-mcp[local-voice]'`` (Pipecat with Kokoro and MLX Whisper).
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from manifest_cli.agents import LocalAgent

VOICE_PORT = int(os.environ.get("MANIFEST_VOICE_PORT") or 47822)
DEFAULT_VOICE = "af_heart"  # Kokoro's most natural English voice
# Quantized: much less memory than the full model, nearly the same accuracy.
STT_MODEL = os.environ.get("MANIFEST_VOICE_STT_MODEL") or "mlx-community/whisper-large-v3-turbo-q4"
NUDGES = ("One moment.", "Let me check.", "Give me a second.", "On it.")
NUDGE_AFTER_SECONDS = 2.0
# After the person stops, wait this long before asking the agent: a question spoken in two
# sentences ("What's a cold chain? Keep it short.") then reaches it as one.
SETTLE_SECONDS = 0.6
# A spoken piece whose transcript never comes (a cough) stops holding the question after this.
MAX_TRANSCRIPT_WAIT_SECONDS = 4.0
TOOL_PREFIX = "mcp__plugin_manifest_manifest__"


# Below this, Whisper + Kokoro next to the agent push the Mac into swap and every reply
# waits seconds (8 GB M1, 2026-11-20: 3–6 s before the first word). The browser speaks instead.
MIN_MEMORY_BYTES = 15 * 1024**3


def enough_memory() -> bool:
    """True when this computer has room for the local speech models (about 16 GB or more)."""
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return False
    return total >= MIN_MEMORY_BYTES


def available() -> str | None:
    """None when local voice can run here, else what's missing."""
    try:
        import mlx_whisper  # noqa: F401
        import pipecat.services.kokoro.tts  # noqa: F401
        import pipecat.services.whisper.stt  # noqa: F401
    except BaseException:  # pipecat raises on a missing optional dependency
        return "Local voice needs: pip install 'manifest-mcp[local-voice]' (Apple silicon)."
    return None


def last_user_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                return " ".join(
                    str(p.get("text") or "") for p in content if isinstance(p, dict)
                ).strip()
    return ""


def context_line(data: Any) -> str:
    """Same line as the bridge's text turns: the idea by title, its id only for tools."""
    from manifest_cli.bridge import describe_context

    return describe_context(data)


def brain_class() -> type:  # noqa: C901 (one class, built lazily so Pipecat loads only for voice)
    from pipecat.frames.frames import (
        InterruptionFrame,
        LLMContextFrame,
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
        VADUserStartedSpeakingFrame,
        VADUserStoppedSpeakingFrame,
    )
    from pipecat.processors.frame_processor import FrameProcessor

    class AgentBrain(FrameProcessor):
        """Where the LLM would be: the person's agent answers each turn, sentence by sentence."""

        def __init__(self, agent: LocalAgent, notify: Any, log: Any = None) -> None:
            super().__init__()
            self.agent, self.notify = agent, notify
            self.log = log or (lambda _line: None)
            self.context = ""
            self._turn = 0
            self._lock = asyncio.Lock()
            self._heard: list[str] = []  # what the person said since the last question
            self._consumed = 0  # user messages already sent to the agent
            self._pending: asyncio.Task[None] | None = None
            self._speaking = False  # an answer for the current turn has started
            self._cut = -1  # answers of turns up to this one were interrupted: stay quiet
            self._talking = False  # the person is speaking right now (VAD)
            self._spoken = 0  # pieces spoken since the last question (VAD stops)
            self._transcribed = 0  # of those, how many have been transcribed

        async def process_frame(self, frame: Any, direction: Any) -> None:
            await super().process_frame(frame, direction)
            if isinstance(frame, LLMContextFrame):
                messages = [m for m in frame.context.get_messages() if isinstance(m, dict)]
                users = [m for m in messages if m.get("role") == "user"]
                for message in users[self._consumed :]:
                    text = last_user_text([message])
                    if text:
                        self._heard.append(text)
                    self._transcribed += 1
                self._consumed = len(users)
                self._schedule()
                return
            if isinstance(frame, VADUserStartedSpeakingFrame):
                self._talking = True
            elif isinstance(frame, VADUserStoppedSpeakingFrame):
                self._talking = False
                self._spoken += 1
            elif isinstance(frame, InterruptionFrame) and self._speaking:
                self._cut = self._turn  # cut off the answer being spoken
                self._speaking = False
            await self.push_frame(frame, direction)

        def _schedule(self) -> None:
            if self._pending is None:
                self._pending = asyncio.ensure_future(self._ask_when_finished())

        async def _ask_when_finished(self) -> None:
            """Ask once the person has stopped and every piece they said is transcribed."""
            waited = 0.0
            await asyncio.sleep(SETTLE_SECONDS)
            while (self._talking or self._transcribed < self._spoken) and (
                waited < MAX_TRANSCRIPT_WAIT_SECONDS
            ):
                await asyncio.sleep(0.1)
                waited += 0.1
            text, self._heard = " ".join(self._heard).strip(), []
            self._spoken = self._transcribed = 0
            self._pending = None
            if text:
                self._turn += 1
                self._speaking = False
                self.log(f"voice: ask (turn {self._turn}): {text[:80]}")
                await self._answer(text, self._turn)

        async def _say(self, text: str, turn: int, *, filler: bool = False) -> None:
            if turn <= self._cut:
                self.log(f"voice: dropped (interrupted turn {turn}): {text[:60]}")
                return
            self.log(f"voice: say (turn {turn}{', filler' if filler else ''}): {text[:60]}")
            if not filler:  # a filler ("One moment.") isn't the answer; talking over it is fine
                self._speaking = True
            await self.push_frame(LLMFullResponseStartFrame())
            await self.push_frame(LLMTextFrame(text + " "))
            await self.push_frame(LLMFullResponseEndFrame())

        async def _event(self, kind: str, value: str, turn: int) -> bool:
            """Speak or show one agent event; True when it changed the person's Manifest data."""
            if kind == "say":
                from manifest_cli.agents import speakable

                if speakable(value):
                    await self._say(speakable(value), turn)
            elif kind == "error":
                await self._say(f"{self.agent.name} ran into a problem.", turn)
            elif kind == "tool":
                label = value.removeprefix(TOOL_PREFIX).replace("_", " ")
                tool = {"type": "manifest.tool", "id": f"t{turn}-{label}", "name": value}
                await self.notify(
                    {**tool, "label": label, "phase": "finished", "ok": True, "summary": "Done"}
                )
                return value.startswith(TOOL_PREFIX)
            return False

        async def _answer(self, text: str, turn: int) -> None:
            prompt = " ".join(p for p in (self.context, text) if p)
            spoke = asyncio.Event()

            async def nudge() -> None:
                await asyncio.sleep(NUDGE_AFTER_SECONDS)
                if not spoke.is_set():
                    await self._say(random.choice(NUDGES), turn, filler=True)

            nudger = asyncio.ensure_future(nudge())
            changed = False
            try:
                async with self._lock:  # one agent turn at a time, in order
                    async for kind, value in self.agent.turn(prompt):
                        if kind in ("say", "error"):
                            spoke.set()
                        changed = await self._event(kind, value, turn) or changed
            except Exception:
                await self._say(f"I couldn't reach {self.agent.name}.", turn)
            finally:
                nudger.cancel()
            if changed:
                await self.notify({"type": "manifest.changed", "tool": "agent"})

    return AgentBrain


async def run_session(
    agent: LocalAgent, *, origins: tuple[str, ...], voice: str, out: TextIO
) -> None:
    """Serve one conversation on the voice port; returns when the person hangs up."""
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
    )
    from pipecat.serializers.protobuf import ProtobufFrameSerializer
    from pipecat.services.kokoro.tts import KokoroTTSService
    from pipecat.services.whisper.stt import WhisperSTTServiceMLX
    from pipecat.transports.websocket.server import (
        SingleClientWebsocketServerParams,
        SingleClientWebsocketServerTransport,
    )
    from pipecat.workers.runner import WorkerRunner

    transport = SingleClientWebsocketServerTransport(
        host="127.0.0.1",
        port=VOICE_PORT,
        params=SingleClientWebsocketServerParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(),
            allowed_origins=list(origins),  # only Manifest's pages may talk to the agent
        ),
    )
    worker_ref: dict[str, Any] = {}

    async def notify(data: dict[str, Any]) -> None:
        worker = worker_ref.get("worker")
        if worker is not None:
            await worker.rtvi.send_server_message(data)

    def log(line: str) -> None:
        out.write(f"{line}  @{time.time():.3f}\n")
        out.flush()

    brain = brain_class()(agent, notify, log)
    user, _assistant = LLMContextAggregatorPair(
        LLMContext(), user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    )
    pipeline = Pipeline(
        [
            transport.input(),
            WhisperSTTServiceMLX(settings=WhisperSTTServiceMLX.Settings(model=STT_MODEL)),
            user,
            brain,
            # Under load Kokoro can take over 3 s to start a sentence; Pipecat's default would
            # then end it as "no audio" (an error the app showed as a red orb).
            KokoroTTSService(
                settings=KokoroTTSService.Settings(voice=voice), stop_frame_timeout_s=12.0
            ),
            transport.output(),
        ]
    )
    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True))
    worker_ref["worker"] = worker

    @worker.rtvi.event_handler("on_client_message")
    async def on_client_message(_rtvi: Any, message: Any) -> None:
        if getattr(message, "type", None) == "manifest.context":
            brain.context = context_line(getattr(message, "data", None))

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport: Any, _client: Any) -> None:
        out.write("voice: connected\n")
        out.flush()
        await brain._say(f"Hi. {agent.name} is here. What's on your mind?", brain._turn)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport: Any, _client: Any) -> None:
        out.write("voice: disconnected\n")
        out.flush()
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()


async def serve_forever(
    agent: LocalAgent, *, origins: tuple[str, ...], voice: str, out: TextIO
) -> None:
    """One conversation after another, for as long as the bridge runs."""
    pause = 1.0
    while True:
        try:
            await run_session(agent, origins=origins, voice=voice, out=out)
            pause = 1.0
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # keep serving; a broken session must not end the bridge
            out.write(f"voice: session ended with {type(exc).__name__}: {exc}\n")
            out.flush()
            await asyncio.sleep(pause)
            pause = min(pause * 2, 60.0)  # don't spin on a lasting problem
