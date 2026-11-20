"""`manifest voice`: talk to Manifest from the terminal.

The CLI is a thin audio bridge to the same live voice agent the web app uses
(``/api/voice-agent/live``, a Pipecat pipeline speaking RTVI over protobuf frames).
Speech recognition, the model, Manifest's tools and speech synthesis all run on the
server with your own OpenAI key, so the agent can do everything the CLI and plugin can.

Optional extra: ``pip install 'manifest-mcp[voice]'`` (websockets + sounddevice).
``--text`` needs only websockets: type instead of speaking, and read the replies.

Laptop speakers feed back into the microphone, so by default the mic is muted while
Manifest is speaking. With headphones, ``--barge-in`` lets you interrupt it.

``--agent claude|codex|"<command>"`` keeps the voice but swaps the brain: the server only
listens and speaks (relay mode) and your own agent answers each turn on this computer,
with its own tools and history (see ``agents.py``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from manifest_cli.agents import LocalAgent
from urllib.parse import urlencode, urlsplit, urlunsplit

IN_RATE = 16000
OUT_RATE = 24000
CHUNK_MS = 20
RTVI_VERSION = "2.3.0"
# Say something if the agent has been quiet this long, so silence never feels broken.
WORKING_AFTER_SECONDS = 2.5

# ---- minimal protobuf for pipecat's frames.proto -------------------------------------
# Frame { oneof frame { TextFrame text = 1; AudioRawFrame audio = 2;
#   TranscriptionFrame transcription = 3; MessageFrame message = 4; ... } }
# AudioRawFrame { uint64 id = 1; string name = 2; bytes audio = 3; uint32 sample_rate = 4;
#   uint32 num_channels = 5; optional uint64 pts = 6; }   MessageFrame { string data = 1; }


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _field(number: int, payload: bytes) -> bytes:
    return _varint(number << 3 | 2) + _varint(len(payload)) + payload


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def _fields(data: bytes) -> dict[int, Any]:
    out: dict[int, Any] = {}
    pos = 0
    while pos < len(data):
        key, pos = _read_varint(data, pos)
        number, wire = key >> 3, key & 7
        if wire == 0:
            out[number], pos = _read_varint(data, pos)
        elif wire == 2:
            length, pos = _read_varint(data, pos)
            out[number] = data[pos : pos + length]
            pos += length
        elif wire == 1:
            pos += 8
        elif wire == 5:
            pos += 4
        else:
            raise ValueError("unsupported protobuf wire type")
    return out


def encode_audio(pcm: bytes, sample_rate: int = IN_RATE) -> bytes:
    inner = _field(3, pcm) + _varint(4 << 3) + _varint(sample_rate) + _varint(5 << 3) + _varint(1)
    return _field(2, inner)


def encode_message(data: dict[str, Any]) -> bytes:
    return _field(4, _field(1, json.dumps(data).encode()))


def decode(frame: bytes) -> tuple[str, Any]:
    """("audio", pcm) | ("message", dict) | ("other", None)."""
    top = _fields(frame)
    if 2 in top:
        return "audio", _fields(top[2]).get(3, b"")
    if 4 in top:
        raw = _fields(top[4]).get(1, b"{}")
        try:
            return "message", json.loads(raw)
        except ValueError:
            return "other", None
    return "other", None


def rtvi(kind: str, data: Any = None) -> dict[str, Any]:
    return {"label": "rtvi-ai", "type": kind, "id": uuid.uuid4().hex[:8], "data": data}


def live_url(base_url: str, mode: str = "agent") -> str:
    parts = urlsplit(base_url.rstrip("/"))
    scheme = "wss" if parts.scheme == "https" else "ws"
    query = {"path": "/cli", **({"mode": mode} if mode != "agent" else {})}
    return urlunsplit(
        (scheme, parts.netloc, parts.path + "/api/voice-agent/live", urlencode(query), "")
    )


CLOSE_REASONS = {
    4401: "Sign in first: manifest login",
    4402: "Add your OpenAI key in Manifest → Account → AI settings, then try again.",
    4403: "This origin may not use voice.",
    4503: "Voice isn't available on this server yet.",
}


@dataclass
class Printer:
    out: TextIO
    color: bool

    def _paint(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def line(self, who: str, text: str) -> None:
        label = self._paint("2", "you") if who == "you" else self._paint("1", who)
        self.out.write(f"{label}  {text}\n")
        self.out.flush()

    def note(self, text: str) -> None:
        self.out.write(self._paint("2", f"  · {text}") + "\n")
        self.out.flush()


class VoiceClient:
    """One conversation. Audio I/O is injected so tests can run without a sound card."""

    def __init__(
        self,
        url: str,
        token: str,
        printer: Printer,
        *,
        barge_in: bool = False,
        agent: LocalAgent | None = None,
    ) -> None:
        self.url, self.token, self.printer, self.barge_in = url, token, printer, barge_in
        self.agent = agent
        self.speaker = agent.name.lower() if agent else "manifest"
        self.turns: asyncio.Queue[str] = asyncio.Queue()
        self.bot_speaking = False
        self.text_mode = False
        self.ended = asyncio.Event()
        self._bot_line: list[str] = []

    def handle(self, message: dict[str, Any]) -> None:
        kind, data = message.get("type"), message.get("data") or {}
        if kind == "bot-ready":
            via = f" to {self.agent.name}" if self.agent else ""
            self.printer.note(
                f"connected{via}"
                if self.text_mode
                else f"connected{via}; just talk (Ctrl-C to stop)"
            )
        elif kind == "user-transcription" and data.get("final"):
            self.printer.line("you", str(data.get("text", "")).strip())
        elif kind == "bot-output" and data.get("aggregated_by") != "word":
            text = str(data.get("text", "")).strip()
            if text and (not self._bot_line or self._bot_line[-1] != text):
                self._bot_line.append(text)
                self.printer.line(self.speaker, text)
        elif kind == "bot-started-speaking":
            self.bot_speaking = True
        elif kind == "bot-stopped-speaking":
            self.bot_speaking = False
            self._bot_line.clear()
        elif kind == "server-message":
            self._server_message(data)
        elif kind == "error":
            self.printer.note(f"error: {data.get('error') or data}")

    def _server_message(self, data: dict[str, Any]) -> None:
        kind = data.get("type")
        if kind == "manifest.tool" and data.get("phase") == "finished":
            mark = "✓" if data.get("ok") else "✗"
            summary = data.get("summary") or ""
            self.printer.note(
                f"{mark} {data.get('label')}{' — ' + summary if summary != 'Done' else ''}"
            )
        elif kind == "manifest.navigate":
            self.printer.note(f"open in the app: {data.get('path')}")
        elif kind == "manifest.end":
            self.ended.set()
        elif kind == "manifest.turn" and self.agent is not None:
            text = str(data.get("text") or "").strip()
            if text:
                self.turns.put_nowait(text)

    async def _say(self, ws: Any, text: str) -> None:
        await ws.send(
            encode_message(rtvi("client-message", {"t": "manifest.say", "d": {"text": text}}))
        )

    async def _nudge(self, ws: Any, spoke: asyncio.Event) -> None:
        await asyncio.sleep(WORKING_AFTER_SECONDS)
        if not spoke.is_set():
            await self._say(ws, "Working on it.")

    async def _relay(self, ws: Any) -> None:
        """Answer each turn with the person's own agent, speaking as it goes."""
        assert self.agent is not None
        agent = self.agent
        warm = getattr(agent, "start", None)
        if warm is not None:  # start a long-lived agent now, while the person talks
            asyncio.ensure_future(warm())
        await self._say(ws, f"{agent.name} is listening.")
        while True:
            texts = [await self.turns.get()]
            while not self.turns.empty():  # spoke again while the agent was busy: one turn
                texts.append(self.turns.get_nowait())
            spoke = asyncio.Event()

            nudger = asyncio.create_task(self._nudge(ws, spoke))
            try:
                async for kind, value in agent.turn(" ".join(texts)):
                    if kind == "say":
                        spoke.set()
                        await self._say(ws, value)
                    elif kind == "tool":
                        self.printer.note(f"{agent.name}: {value}")
                    elif kind == "error":
                        self.printer.note(f"{agent.name}: {value}")
                        spoke.set()
                        await self._say(
                            ws, f"{agent.name} ran into a problem. Details are in the terminal."
                        )
            except FileNotFoundError:
                self.printer.note(f"could not start {agent.name}")
                await self._say(ws, f"I couldn't start {agent.name}.")
            finally:
                nudger.cancel()

    async def run(self, *, text_mode: bool, stdin: TextIO) -> int:
        import websockets

        self.text_mode = text_mode
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with websockets.connect(
                self.url, additional_headers=headers, max_size=None
            ) as ws:
                await ws.send(
                    encode_message(
                        rtvi(
                            "client-ready",
                            {"version": RTVI_VERSION, "about": {"library": "manifest-cli"}},
                        )
                    )
                )
                tasks: list[asyncio.Task[Any]] = [
                    asyncio.create_task(self._receive(ws, play=not text_mode))
                ]
                tasks.append(
                    asyncio.create_task(
                        self._type(ws, stdin) if text_mode else self._microphone(ws)
                    )
                )
                tasks.append(asyncio.create_task(self.ended.wait()))
                if self.agent is not None:
                    tasks.append(asyncio.create_task(self._relay(ws)))
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                if self.agent is not None:
                    self.agent.stop()
                for task in done:
                    if task.exception():
                        raise task.exception()  # type: ignore[misc]
                if self.ended.is_set():
                    await asyncio.sleep(1.5)  # let the goodbye finish playing
        except websockets.exceptions.ConnectionClosed as closed:
            reason = CLOSE_REASONS.get(closed.rcvd.code if closed.rcvd else 0)
            if reason:
                self.printer.note(reason)
                return 1
        except (OSError, websockets.exceptions.InvalidStatus) as exc:
            self.printer.note(f"could not reach Manifest voice: {exc}")
            return 1
        return 0

    async def _receive(self, ws: Any, *, play: bool) -> None:
        stream = None
        if play:
            import sounddevice as sd

            stream = sd.RawOutputStream(samplerate=OUT_RATE, channels=1, dtype="int16")
            stream.start()
        try:
            async for raw in ws:
                if isinstance(raw, str):
                    continue
                kind, value = decode(raw)
                if kind == "audio" and stream is not None:
                    await asyncio.to_thread(stream.write, value)
                elif kind == "message":
                    self.handle(value)
        finally:
            if stream is not None:
                stream.stop()
                stream.close()

    async def _microphone(self, ws: Any) -> None:
        import sounddevice as sd

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        frames = IN_RATE * CHUNK_MS // 1000
        silence = b"\x00\x00" * frames

        def callback(indata: Any, _frames: int, _time: Any, _status: Any) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, bytes(indata))

        with sd.RawInputStream(
            samplerate=IN_RATE, channels=1, dtype="int16", blocksize=frames, callback=callback
        ):
            while True:
                chunk = await queue.get()
                muted = self.bot_speaking and not self.barge_in
                await ws.send(encode_audio(silence if muted else chunk))

    async def _type(self, ws: Any, stdin: TextIO) -> None:
        self.printer.note("text mode: type a message and press Enter (Ctrl-D to stop)")
        while True:
            line = await asyncio.to_thread(stdin.readline)
            if not line:
                return
            text = line.strip()
            if text:
                await ws.send(
                    encode_message(
                        rtvi(
                            "send-text",
                            {
                                "content": text,
                                "options": {"run_immediately": True, "audio_response": False},
                            },
                        )
                    )
                )


def missing_audio_support() -> str | None:
    try:
        import sounddevice  # noqa: F401
        import websockets  # noqa: F401
    except Exception:
        return "Voice needs two extra packages: pip install 'manifest-mcp[voice]'  (or use --text)"
    return None


def run(
    base_url: str,
    token: str,
    *,
    out: TextIO,
    stdin: TextIO,
    text_mode: bool,
    barge_in: bool,
    agent: LocalAgent | None = None,
) -> int:
    color = out.isatty() if hasattr(out, "isatty") else False
    url = live_url(base_url, "relay" if agent else "agent")
    client = VoiceClient(url, token, Printer(out, color), barge_in=barge_in, agent=agent)
    with contextlib.suppress(KeyboardInterrupt):
        return asyncio.run(client.run(text_mode=text_mode, stdin=stdin))
    out.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(
        run(
            sys.argv[1],
            sys.argv[2],
            out=sys.stdout,
            stdin=sys.stdin,
            text_mode=True,
            barge_in=False,
        )
    )
