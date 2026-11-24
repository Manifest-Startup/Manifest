"""`manifest bridge`: let the Manifest web app talk to the agent on this computer.

    Manifest web app / installed Chrome app ── http://127.0.0.1:47821 ──▶ Claude Code / Codex
                                     (Safari) ── https://127.0.0.1:47823 (bridge_tls.py)

Voice in the app needs no OpenAI key this way: the browser listens and speaks with its own
speech recognition and voices, and each turn goes to the agent you already use (with its
own tools, permissions and history), through this small local server.

Safety: it listens on 127.0.0.1 only and answers only pages from Manifest's own origins
(browsers send an Origin header that web pages cannot fake), so other websites cannot
drive your agent. The agent keeps its own permission rules (Claude Code is read-only by
default here; see ``agents.py``).

    GET  /health   {"ok", "agent", "agent_id", "ready", "problems": [{code, message, fix}], "agents",
                    "choice", "folder", "voice", "interrupt", "speech", "speech_status"}
    POST /agent    {"agent": "codex" | "claude" | "active"} → switch now (saved); 409 + error if not ready
    POST /turn     {"text": "...", "context": {"path", "idea_id", "idea_title"}}
                   → newline-delimited JSON: {"kind": "say"|"tool"|"error", "text"}…
                     then {"kind": "done"}. Closing the connection early interrupts the
                     agent (the person talked over it).
    POST /speak    {"text": "One sentence."} → 16-bit mono PCM, 24 kHz (Kokoro; see speech.py)
    POST /speak/warm   page the voice model in while the person is still talking
    GET  /vault/folder   where this computer keeps the vault (see ``vault_folder.where``)
    POST /vault/folder   {"place": "icloud" | "documents" | "home" | "/full/path"} → moves it;
                         {"on_delete": "delete" | "keep"} → what a note deleted in Manifest does here
    POST /vault/sync     sync this computer's vault with the account now (pull to refresh)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import plistlib
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from manifest_cli import bridge_setup as setup
from manifest_cli import speech
from manifest_cli.agents import speakable
from manifest_cli.speech import Voice

if TYPE_CHECKING:
    from manifest_cli.agents import LocalAgent

DEFAULT_PORT = 47821
DEFAULT_ORIGINS = (
    "https://manifeststartup.com",
    "https://www.manifeststartup.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)
MAX_BODY = 64 * 1024


def describe_context(context: Any) -> str:
    """One line telling the agent what the person is looking at in Manifest."""
    if not isinstance(context, dict):
        return ""
    title = str(context.get("idea_title") or "").strip()[:200]
    idea = str(context.get("idea_id") or "").strip()[:80]
    path = str(context.get("path") or "").strip()[:200]
    if idea:
        # The id is for tools only: people never see ids in the app (issue #114).
        if title:
            return (
                f'(In the Manifest app, the person is looking at the idea "{title}"; '
                f"its id for tools is {idea}. Call it by its title, never by the id.)"
            )
        return (
            f"(In the Manifest app, the person is looking at an idea whose id for tools is "
            f"{idea}. Look up its title before you name it; never say the id.)"
        )
    return f"(In the Manifest app, the person is on {path}.)" if path else ""


_SWITCH = re.compile(
    r"^\W*(?:ok(?:ay)?\W+|hey\W+|please\W+)*(?:switch|change|go back|move|hand (?:it )?over)"
    r"(?:\s+(?:over|back))?\s+to\s+(claude(?:\s+code)?|codex)\b"
    r"|^\W*(?:please\W+)?(?:use|talk to)\s+(claude(?:\s+code)?|codex)(?:\s+(?:now|instead))?\W*$",
    re.IGNORECASE,
)
# A new conversation after this long picks the agent used most recently again.
IDLE_RESELECT_S = 120.0
HANDOFF_TURNS = 12


def switch_request(text: str) -> str | None:
    """ "Switch to Codex", "use Claude Code instead" → the agent's key; else None."""
    match = _SWITCH.search(text.strip())
    if not match:
        return None
    return "codex" if "codex" in (match.group(1) or match.group(2) or "").lower() else "claude"


class AgentPool:
    """The agents set up for voice (issue #132). One answers at a time: the one the person
    chose, or by default the one they used most recently on this computer. Each agent keeps
    its own session, and a switch hands the new agent this conversation so far, so it picks
    up where the other left off."""

    def __init__(
        self,
        settings: setup.BridgeSettings | None = None,
        *,
        agent: LocalAgent | None = None,
        save_to: Path | None = None,
    ) -> None:
        from collections import deque

        self.settings = settings or setup.BridgeSettings()
        self.save_to = save_to  # persist switches here (the saved settings file)
        self.live: dict[str, LocalAgent] = {}
        self.problems: dict[str, list[setup.Problem]] = {}
        self.history: deque[tuple[str, str]] = deque(maxlen=HANDOFF_TURNS * 2)
        self.handoff: dict[str, str] = {}  # agent key → conversation to hand it on its next turn
        self.last_turn = 0.0
        self.current_key: str | None = None
        if agent is not None:  # one fixed agent (tests, `manifest voice`)
            key = _key_of(agent)
            self.live[key], self.current_key = agent, key
            self.settings.agents.setdefault(key, setup.AgentProfile(workdir=agent.cwd or ""))
            self.settings.default = key
            self.problems[key] = []

    def check(self, *, auth: bool = True) -> None:
        for key, profile in self.settings.agents.items():
            if key not in self.live or key not in self.problems:
                self.problems[key] = setup.check_agent(key, profile, auth=auth)

    def ready_keys(self) -> list[str]:
        return [k for k in self.settings.agents if not self.problems.get(k)]

    def resolve(self) -> str | None:
        """The agent that answers next."""
        choice = self.settings.default
        if choice != setup.ACTIVE:
            return choice  # chosen explicitly: never silently another agent
        ready = self.ready_keys()
        return (
            setup.active_agent(ready)
            or (ready[0] if ready else None)
            or next(iter(self.settings.agents), None)
        )

    def refresh(self) -> None:
        """A new conversation: pick the agent used most recently again (when not chosen)."""
        if self.settings.default != setup.ACTIVE:
            self.select(self.settings.default)
        elif time.monotonic() - self.last_turn > IDLE_RESELECT_S or self.current_key is None:
            key = self.resolve()
            if key:
                self.select(key)

    def select(self, key: str) -> None:
        if key == self.current_key:
            return
        previous = self.current_key
        self.current_key = key
        if previous and self.history:
            lines = "\n".join(f"{who}: {text}" for who, text in self.history)
            self.handoff[key] = (
                f"(This voice conversation in Manifest was with {setup.agent_name(previous)} "
                f"until now; the person switched to you. Here it is so far, so you can carry on "
                f"where it left off without asking again:\n{lines}\n)"
            )

    def switch(self, key: str) -> setup.Problem | None:
        """Switch now (and remember it): by voice, in the app or `manifest bridge --use`."""
        key = setup.agent_key(key)
        if key != setup.ACTIVE:
            if key not in self.settings.agents:
                if key not in setup.KNOWN_AGENTS:
                    return setup.Problem(
                        setup.NO_AGENT, f"{key} isn't an agent.", "Say Claude Code or Codex."
                    )
                profile = setup.AgentProfile(workdir=setup.suggested_folder(key))
                self.settings.agents[key] = profile
                self.problems.pop(key, None)
            self.problems.pop(key, None)  # check again: the person may have fixed it
            self.check()
            if self.problems.get(key):
                return self.problems[key][0]
        self.settings.default = key
        if self.save_to:
            with contextlib.suppress(OSError, ValueError):
                setup.save(self.settings, self.save_to)
        target = self.resolve()
        if target:
            self.select(target)
        return None

    def agent(self, key: str | None = None) -> LocalAgent:
        key = key or self.current_key or self.resolve() or "claude"
        if key not in self.live:
            from manifest_cli.agents import make_agent

            profile = self.settings.agents.get(key) or setup.AgentProfile()
            self.live[key] = make_agent(
                key,
                extra_args=profile.agent_args,
                resume=profile.resume,
                continue_last=profile.continue_last,
                model=profile.model,
                cwd=str(profile.folder),
            )
        if self.current_key is None:
            self.current_key = key
        return self.live[key]

    def prompt_for(self, key: str, prompt: str) -> str:
        handoff = self.handoff.pop(key, "")
        return f"{handoff}\n\n{prompt}" if handoff else prompt

    def remember(self, who: str, text: str) -> None:
        if text.strip():
            self.history.append((who, " ".join(text.split())[:600]))

    def status(self) -> dict[str, Any]:
        key = self.current_key or self.resolve()
        problems = (
            self.problems.get(key or "", [])
            if key
            else [
                setup.Problem(
                    setup.NO_AGENT, "No agent is set up.", "Run `manifest bridge --install`."
                )
            ]
        )
        return {
            "agent_id": key,
            "choice": self.settings.default,
            "ready": key is not None and not problems,
            "problems": [p.public() for p in problems],
            "folder": (self.settings.agents.get(key or "") or setup.AgentProfile()).folder.name
            if key
            else None,
            "agents": [
                {
                    "id": k,
                    "name": setup.agent_name(k),
                    "ready": not self.problems.get(k),
                    "problem": (self.problems.get(k) or [None])[0].message  # type: ignore[union-attr]
                    if self.problems.get(k)
                    else None,
                }
                for k in self.settings.agents
            ],
        }

    def stop(self) -> None:
        for agent in self.live.values():
            agent.stop()


def _key_of(agent: LocalAgent) -> str:
    from manifest_cli.agents import ClaudeCodeAgent, CodexAgent, CommandAgent

    if isinstance(agent, ClaudeCodeAgent):
        return "claude"
    if isinstance(agent, CodexAgent):
        return "codex"
    return agent.shell_command if isinstance(agent, CommandAgent) else agent.name


_TONE_LABELS = {
    "energized": "sounds energized",
    "calm": "sounds calm",
    "subdued": "sounds quieter and lower in energy",
}
_TONE_SIGNS = {
    "faster than usual",
    "slower than usual",
    "louder than usual",
    "quieter than usual",
    "more animated pitch than usual",
    "flatter pitch than usual",
    "higher pitch than usual",
    "lower pitch than usual",
}


def describe_tone(tone: Any) -> str:
    """The opt-in tone-of-voice cue the app measured on the person's device (ADR 0024), as one
    line for the agent. Only known labels and phrases pass, so the page can't inject text."""
    if not isinstance(tone, dict):
        return ""
    label = _TONE_LABELS.get(str(tone.get("label") or ""))
    if not label:  # "steady" (their usual self) adds nothing: no extra words for the agent
        return ""
    try:
        confidence = float(tone.get("confidence") or 0)
    except (TypeError, ValueError):
        return ""
    if confidence < 0.3:
        return ""
    signs = [s for s in tone.get("signs") or [] if isinstance(s, str) and s in _TONE_SIGNS][:3]
    how = f" ({', '.join(signs)})" if signs else ""
    return (
        f"(Voice cue from their device, vs. earlier in this call: {label}{how}. A rough hint for "
        "your energy and pace, not a fact; don't mention it.)"
    )


class Bridge:
    def __init__(
        self,
        agent: LocalAgent | AgentPool,
        *,
        origins: tuple[str, ...],
        out: TextIO,
        voice_url: str | None = None,
        speech: Voice | None = None,
        speech_problem: str | None = None,
    ) -> None:
        self.pool = agent if isinstance(agent, AgentPool) else AgentPool(agent=agent)
        self.origins, self.out = origins, out
        self.voice_url = voice_url  # the local Pipecat voice, when it runs here
        self.speech = speech  # Kokoro on the Apple GPU, for /speak
        # Why there's no natural voice on a Mac that could have one (a reinstall without the
        # natural-voice extra, issue #108); None when it's off on purpose or not possible.
        self.speech_problem = speech_problem
        self.lock = asyncio.Lock()

    @property
    def agent(self) -> LocalAgent:
        """The agent answering now."""
        return self.pool.agent()

    def _health(self) -> dict[str, Any]:
        if not self.lock.locked():
            self.pool.refresh()  # a new conversation may pick up the agent used last
        return {
            "ok": True,
            "agent": self.agent.name,
            **self.pool.status(),
            "voice": self.voice_url,
            "interrupt": True,  # a hung-up /turn stops the agent's answer
            # The natural voice (POST /speak), once its model has loaded.
            "speech": self.speech.voice if self.speech and self.speech.ready else None,
            # "ready", "loading", or what's wrong; the app upgrades once it's ready.
            "speech_status": getattr(self.speech, "status", "ready")
            if self.speech
            else (self.speech_problem or "off"),
        }

    def _cors(self, origin: str) -> list[str]:
        return [
            f"Access-Control-Allow-Origin: {origin}",
            "Vary: Origin",
            "Access-Control-Allow-Methods: GET, POST, OPTIONS",
            "Access-Control-Allow-Headers: content-type",
            "Access-Control-Expose-Headers: X-Sample-Rate",
            # Chrome asks before a public site may reach a local server.
            "Access-Control-Allow-Private-Network: true",
        ]

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await self._handle(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError, ValueError):
            pass
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = (await reader.readline()).decode("latin-1").split()
        if len(request) < 2:
            return
        method, path = request[0], request[1]
        headers: dict[str, str] = {}
        while True:
            line = (await reader.readline()).decode("latin-1").strip()
            if not line:
                break
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        origin = headers.get("origin", "")

        def send(status: str, extra: list[str], body: bytes = b"") -> None:
            head = [
                f"HTTP/1.1 {status}",
                *extra,
                f"Content-Length: {len(body)}",
                "Connection: close",
            ]
            writer.write(("\r\n".join(head) + "\r\n\r\n").encode() + body)

        if origin not in self.origins:
            send(
                "403 Forbidden",
                ["Content-Type: text/plain"],
                b"Only the Manifest app may use this bridge.",
            )
            await writer.drain()
            return
        cors = self._cors(origin)
        if method == "OPTIONS":
            send("204 No Content", cors)
        elif method == "GET" and path == "/health":
            body = json.dumps(self._health()).encode()
            send("200 OK", [*cors, "Content-Type: application/json"], body)
        elif (path, method) == ("/agent", "POST") or (
            path in ("/vault/folder", "/vault/sync") and method in ("GET", "POST")
        ):
            length = int(headers.get("content-length") or 0)
            status, body = await (
                self._switch_agent(reader, length)
                if path == "/agent"
                else self._vault_sync(method)
                if path == "/vault/sync"
                else self._vault_folder(method, reader, length)
            )
            send(status, [*cors, "Content-Type: application/json"], json.dumps(body).encode())
        elif method == "POST" and path in ("/speak", "/speak/warm"):
            length = int(headers.get("content-length") or 0)
            status, extra, audio = await self._speak(path, reader, length)
            send(status, [*cors, *extra], audio)
        elif method == "POST" and path == "/turn":
            length = int(headers.get("content-length") or 0)
            if length <= 0 or length > MAX_BODY:
                send("413 Payload Too Large", cors)
            else:
                payload = json.loads(await reader.readexactly(length))
                await self._turn(reader, writer, cors, payload if isinstance(payload, dict) else {})
                return
        else:
            send("404 Not Found", cors)
        await writer.drain()

    async def _switch_agent(
        self, reader: asyncio.StreamReader, length: int
    ) -> tuple[str, dict[str, Any]]:
        """The app (or `manifest bridge --use`) switches the agent that answers."""
        if length <= 0 or length > MAX_BODY:
            return "413 Payload Too Large", {"error": 'Send {"agent": ...}.'}
        payload = json.loads(await reader.readexactly(length))
        key = str(payload.get("agent") or "") if isinstance(payload, dict) else ""
        async with self.lock:  # never mid-answer
            problem = self.pool.switch(key)
        if not problem:
            self.out.write(f"agent  now {self.agent.name}\n")
            self.out.flush()
        body = {**self._health(), "error": problem.public() if problem else None}
        return ("409 Conflict" if problem else "200 OK"), body

    async def _speak(
        self, path: str, reader: asyncio.StreamReader, length: int
    ) -> tuple[str, list[str], bytes]:
        """One sentence in the natural voice, or a warm-up while the person talks."""
        if not (self.speech and self.speech.ready):
            return "503 Service Unavailable", [], b""
        if path == "/speak/warm":
            self.speech.warm()
            return "204 No Content", [], b""
        if length <= 0 or length > MAX_BODY:
            return "413 Payload Too Large", [], b""
        payload = json.loads(await reader.readexactly(length))
        text = str(payload.get("text") or "") if isinstance(payload, dict) else ""
        audio = await self.speech.speak(text)
        head = ["Content-Type: application/octet-stream", f"X-Sample-Rate: {speech.SAMPLE_RATE}"]
        return "200 OK", head, audio

    async def _vault_sync(self, method: str) -> tuple[str, dict[str, Any]]:
        """Pull to refresh in the app: sync this computer's vault with the account now."""
        from manifest_cli import vault_folder

        if method != "POST":
            return "405 Method Not Allowed", {"error": "POST to sync."}
        try:
            return "200 OK", await asyncio.to_thread(vault_folder.sync_now)
        except vault_folder.VaultFolderError as exc:
            return "409 Conflict", {"error": str(exc)}

    async def _vault_folder(
        self, method: str, reader: asyncio.StreamReader, length: int
    ) -> tuple[str, dict[str, Any]]:
        from manifest_cli import vault_folder

        try:
            if method == "GET":
                return "200 OK", await asyncio.to_thread(vault_folder.where)
            if length <= 0 or length > MAX_BODY:
                return "413 Payload Too Large", {"error": 'Send {"place": ...}.'}
            payload = json.loads(await reader.readexactly(length))
            payload = payload if isinstance(payload, dict) else {}
            if payload.get("on_delete") is not None and not payload.get("place"):
                result = await asyncio.to_thread(
                    vault_folder.set_on_delete, str(payload["on_delete"])
                )
                self.out.write(f"vault  on delete: {result.get('on_delete')}\n")
                self.out.flush()
                return "200 OK", result
            place = str(payload.get("place") or "")
            result = await asyncio.to_thread(vault_folder.move, place)
            self.out.write(f"vault  moved to {result.get('folder')}\n")
            self.out.flush()
            return "200 OK", result
        except vault_folder.VaultFolderError as exc:
            return "409 Conflict", {"error": str(exc)}

    async def _turn(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        cors: list[str],
        payload: dict,
    ) -> None:
        text = " ".join(str(payload.get("text") or "").split())[:4000]
        head = [
            "HTTP/1.1 200 OK",
            *cors,
            "Content-Type: application/x-ndjson",
            "Cache-Control: no-store",
            "Connection: close",
        ]
        writer.write(("\r\n".join(head) + "\r\n\r\n").encode())

        link = _TurnLink(reader, writer, self)
        emit = link.emit

        if not text:
            await emit("done")
            return
        prompt = " ".join(
            p
            for p in (
                describe_context(payload.get("context")),
                describe_tone(payload.get("tone")),
                text,
            )
            if p
        )
        self.out.write(f"you  {text}\n")
        self.out.flush()
        async with self.lock:  # one turn at a time, in order
            self.pool.refresh()
            wanted = switch_request(text)
            if wanted:
                problem = self.pool.switch(wanted)
                said = (
                    f"{setup.agent_name(wanted)} isn't ready: {problem.message} {problem.fix}"
                    if problem
                    else f"Okay, you're talking to {self.agent.name} now. It knows what we said."
                )
                await emit("error" if problem else "say", said)
                self.pool.remember("Manifest", said)
                await emit("done")
                return
            key = self.pool.current_key or self.pool.resolve() or ""
            agent = self.pool.agent(key or None)
            problems = self.pool.problems.get(key) or []
            if problems:  # don't start an agent that can't answer; say what to do instead
                await emit("error", f"{problems[0].message} {problems[0].fix}")
                await emit("done")
                return
            self.pool.remember("Person", text)
            spoken: list[str] = []
            watcher = asyncio.ensure_future(link.watch())
            try:
                async for kind, value in agent.turn(self.pool.prompt_for(key, prompt)):
                    if kind == "error":
                        profile = self.pool.settings.agents.get(key) or setup.AgentProfile()
                        value = setup.explain_agent_error(key, value, profile.folder)
                    if kind == "say":
                        value = speakable(value)
                        if not value:
                            continue
                    if kind in ("say", "tool", "error") and not link.gone:
                        await emit(kind, value)
                        if kind == "say":
                            spoken.append(value)
                            self.out.write(f"{agent.name.lower()}  {value}\n")
                            self.out.flush()
            except FileNotFoundError:
                await emit("error", f"Could not start {agent.name}.")
            finally:
                watcher.cancel()
                self.pool.remember(agent.name, " ".join(spoken))
                self.pool.last_turn = time.monotonic()
        await emit("done")


class _TurnLink:
    """One /turn connection: streams events to the app, and notices at once when the app
    hangs up (the person talked over the answer) so the agent is interrupted right away."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, bridge: Bridge):
        self.reader, self.writer, self.bridge = reader, writer, bridge
        self.gone = False

    async def hung_up(self) -> None:
        if self.gone:
            return
        self.gone = True
        self.bridge.out.write("you  (interrupted)\n")
        self.bridge.out.flush()
        await self.bridge.agent.interrupt()  # stop the answer; the next turn needn't wait

    async def watch(self) -> None:
        # The request is fully read, so the app's side ends only when it hangs up.
        with contextlib.suppress(ConnectionError):
            while await self.reader.read(1024):
                pass
        await self.hung_up()

    async def emit(self, kind: str, value: str = "") -> None:
        if self.gone:
            return
        try:
            self.writer.write((json.dumps({"kind": kind, "text": value}) + "\n").encode())
            await self.writer.drain()
        except ConnectionError:
            await self.hung_up()


async def serve(
    agent: LocalAgent | AgentPool,
    *,
    port: int = DEFAULT_PORT,
    origins: tuple[str, ...] = DEFAULT_ORIGINS,
    out: TextIO,
    voice: str | None = None,
) -> None:
    from manifest_cli import local_voice

    pool = agent if isinstance(agent, AgentPool) else AgentPool(agent=agent)
    pool.check()
    pool.refresh()
    agent = pool.agent()
    # The natural voice: the browser hears, Kokoro on the Apple GPU speaks (POST /speak).
    no_speech = speech.supported() if voice != "browser" else "browser voice chosen"

    def log(line: str) -> None:
        out.write(line + "\n")
        out.flush()

    natural = None if no_speech else Voice(voice or speech.DEFAULT_VOICE, log=log)
    if natural:
        threading.Thread(target=natural.load_forever, daemon=True).start()  # a few seconds
    missing = local_voice.available() if voice != "browser" else "browser voice chosen"
    if not missing and natural:
        missing = "the natural voice (browser hearing, Kokoro on the GPU) is faster"
    elif not missing and voice is None and not local_voice.enough_memory():
        # Whisper + Kokoro on a small Mac swap and answer in seconds.
        missing = "the browser's speech is faster on this Mac"
    voice_url = None if missing else f"ws://127.0.0.1:{local_voice.VOICE_PORT}"
    # With a Cartesia key: the voice of Pipecat's own demos, Kokoro as its fallback.
    key = speech.cartesia_key() if voice != "browser" else None
    chosen = voice if voice and len(voice) == 36 and voice.count("-") == 4 else speech.PIPECAT_VOICE
    spoken = speech.CartesiaVoice(key, chosen, fallback=natural) if key else natural
    # Missing packages on Apple silicon is a broken install, not a choice: say so to the app.
    fixable = bool(no_speech) and no_speech.startswith("install")
    bridge = Bridge(
        pool,
        origins=origins,
        out=out,
        voice_url=voice_url,
        speech=spoken,
        speech_problem=f"natural voice not installed: {no_speech}" if fixable else None,
    )
    try:
        server = await asyncio.start_server(bridge.handle, "127.0.0.1", port)
    except OSError as exc:
        raise BridgeError(port_in_use(port)) from exc
    # HTTPS too, for Safari (it won't call http://127.0.0.1 from a secure page).
    from manifest_cli import bridge_tls

    secure = await _start_https(bridge, out)
    warm = getattr(agent, "start", None) if pool.status()["ready"] else None
    if warm is not None:
        await warm()  # Claude Code: start once now, so the first turn is quick
    voice_task = None
    if voice_url:
        # Natural voice on this Mac: Pipecat with local Whisper and Kokoro, no key.
        voice_task = asyncio.ensure_future(
            local_voice.serve_forever(
                agent, origins=origins, voice=voice or local_voice.DEFAULT_VOICE, out=out
            )
        )
    status = pool.status()
    names = ", ".join(a["name"] for a in status["agents"]) or "none"
    folder = (pool.settings.agents.get(pool.current_key or "") or setup.AgentProfile()).folder
    lead = "the agent you used last, now " if pool.settings.default == setup.ACTIVE else ""
    out.write(
        f"Bridge listening on http://127.0.0.1:{port}. Agents set up: {names}.\n"
        f"Answers with {lead}{agent.name}, in {folder}.\n"
    )
    for item in status["agents"]:
        if item["problem"]:
            fix = pool.problems[item["id"]][0].fix
            out.write(f"Not ready: {item['name']}: {item['problem']} {fix}\n")
    out.write(
        (
            f"{agent.name} is ready to answer.\n"
            if status["ready"]
            else f"{agent.name} can't answer yet (see above); voice will say why.\n"
        )
        + (
            "Voice: Cartesia (Pipecat's voice), with Kokoro as the fallback.\n"
            if key
            else f"Natural voice: Kokoro ({natural.voice}) on the Apple GPU, loading now.\n"
            if natural
            else f"Natural voice (Pipecat, local Whisper + Kokoro) on {voice_url}.\n"
            if voice_url
            else f"Browser voice only ({no_speech}; {missing}).\n"
        )
        + (
            f"Safari too: https://127.0.0.1:{bridge_tls.HTTPS_PORT}.\n"
            if secure
            else "Safari needs `manifest bridge --install` (HTTPS); Chrome works as is.\n"
        )
        + 'Open Manifest and tap the voice button; say "switch to Codex" (or Claude) any time.\n'
    )
    out.flush()
    async with server:
        try:
            await server.serve_forever()
        finally:
            if voice_task:
                voice_task.cancel()
            if secure:
                secure.close()
            pool.stop()


async def _start_https(bridge: Bridge, out: TextIO) -> asyncio.Server | None:
    from manifest_cli import bridge_tls

    tls = bridge_tls.server_context()
    if not tls:
        return None
    try:
        return await asyncio.start_server(
            bridge.handle, "127.0.0.1", bridge_tls.HTTPS_PORT, ssl=tls
        )
    except OSError:  # another bridge holds it (a second, foreground one): HTTP only
        out.write(f"HTTPS port {bridge_tls.HTTPS_PORT} is in use; Safari uses the other bridge.\n")
        return None


class BridgeError(Exception):
    """A setup problem with a plain message and the next step."""


def port_in_use(port: int) -> str:
    health = setup.bridge_health(port)
    if health:
        return (
            f"A Manifest bridge is already running on port {port} (with {health.get('agent')}). "
            "Switch agents with `manifest bridge --use codex` (or claude), restart it with "
            "`manifest bridge --restart`, or stop the login item with `manifest bridge --uninstall`."
        )
    return (
        f"Port {port} is in use by another program. Quit it, or choose another port with --port "
        "(the app looks on 47821, so self-hosted setups only)."
    )


LAUNCH_LABEL = "com.manifeststartup.bridge"


def launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_LABEL}.plist"


def launch_agent_plist(
    args: list[str],
    *,
    path_env: str,
    log: Path,
    launcher: Path | None = None,
    workdir: Path | None = None,
) -> dict[str, Any]:
    """A login item that keeps `manifest bridge` running (restarted if it stops). With a
    `launcher` (macos_app), it runs as "Manifest Bridge", which may use an iCloud vault."""
    program = ([str(launcher)] if launcher else []) + [sys.executable]
    return {
        "Label": LAUNCH_LABEL,
        "ProgramArguments": [*program, "-m", "manifest_cli", "bridge", *args],
        "RunAtLoad": True,
        "KeepAlive": True,
        # The agent's own folder comes from the saved settings; this is only where the
        # bridge process itself starts.
        "WorkingDirectory": str(workdir or Path.home()),
        "EnvironmentVariables": {"PATH": path_env},
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
        "ProcessType": "Interactive",
    }


def _bootstrap_when_unloaded(
    domain: str, plist: Path, *, timeout: float = 20.0
) -> subprocess.CompletedProcess[str]:
    """Load the agent once launchd has let go of the old one.

    `bootout` returns before the old bridge has exited (Pipecat takes a few
    seconds to stop), and `bootstrap` fails with "5: Input/output error" until
    it has, so wait for the old service to vanish and retry briefly.
    """
    deadline = time.monotonic() + timeout
    target = f"{domain}/{LAUNCH_LABEL}"
    while time.monotonic() < deadline:
        if subprocess.run(["launchctl", "print", target], capture_output=True).returncode:
            break
        time.sleep(0.5)
    while True:
        started = subprocess.run(
            ["launchctl", "bootstrap", domain, str(plist)], capture_output=True, text=True
        )
        if started.returncode == 0 or time.monotonic() >= deadline:
            return started
        time.sleep(1.0)


def install(
    args: list[str], *, out: TextIO, workdir: Path | None = None, port: int = DEFAULT_PORT
) -> int:
    """Run the bridge at login (macOS LaunchAgent), replacing an earlier install, and wait
    until it answers: "Done" only once the installed bridge itself says it is ready."""
    if sys.platform != "darwin":
        out.write(
            "--install sets up a macOS login item. Elsewhere, run `manifest bridge` at startup.\n"
        )
        return 1
    log = Path.home() / "Library" / "Logs" / "Manifest" / "bridge.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    plist = launch_agent_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    from manifest_cli import bridge_tls

    out.write("Safari needs the bridge on HTTPS: macOS may ask for your password once.\n")
    out.flush()
    if not bridge_tls.ensure(ask_to_trust=True):
        out.write("HTTPS isn't set up, so Safari can't reach the bridge (Chrome can).\n")
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{LAUNCH_LABEL}"], capture_output=True)
    from manifest_cli import macos_app

    app = macos_app.launcher("Manifest Bridge", LAUNCH_LABEL)
    with plist.open("wb") as handle:
        plistlib.dump(
            launch_agent_plist(
                args,
                path_env=os.environ.get("PATH", ""),
                log=log,
                launcher=app,
                workdir=workdir,
            ),
            handle,
        )
    started = _bootstrap_when_unloaded(domain, plist)
    if started.returncode != 0:
        out.write(f"Could not start it: {started.stderr.strip() or started.returncode}\n")
        return 1
    out.write("The Manifest bridge now starts when you log in and stays running.\n")
    health = wait_for_bridge(port)
    if health is None:
        out.write(f"It hasn't answered yet; see {log}, or run `manifest bridge --doctor`.\n")
        return 1
    code = 0
    if health.get("ready", True):
        folder = f" · {health['folder']}" if health.get("folder") else ""
        out.write(f"Ready: {health.get('agent')}{folder} · voice works with no key.\n")
    else:
        code = 1
        for problem in health.get("problems") or []:
            out.write(f"Not ready: {problem.get('message')}\n  Next: {problem.get('fix')}\n")
    others = [a for a in health.get("agents") or [] if a.get("id") != health.get("agent_id")]
    for item in others:
        state = "ready" if item.get("ready") else f"not ready ({item.get('problem')})"
        out.write(
            f'Also set up: {item.get("name")}, {state}. Say "switch to {item.get("name")}".\n'
        )
    out.write(
        f"Log: {log}\nCheck: manifest bridge --doctor · Switch: manifest bridge --use codex|claude|active\n"
        "Undo: manifest bridge --uninstall\n"
    )
    return code


def wait_for_bridge(port: int, attempts: int = 60) -> dict[str, Any] | None:
    for _ in range(attempts):
        health = setup.bridge_health(port, timeout=1.0)
        if health is not None:
            return health
        time.sleep(0.5)
    return None


def restart(*, out: TextIO, port: int = DEFAULT_PORT) -> int:
    done = subprocess.run(
        ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LAUNCH_LABEL}"], capture_output=True
    )
    if done.returncode:
        out.write("The bridge isn't installed as a login item: `manifest bridge --install`.\n")
        return 1
    health = wait_for_bridge(port)
    out.write(
        f"Restarted: {health.get('agent')} {'ready' if health.get('ready', True) else 'not ready'}.\n"
        if health
        else "Restarted, but it hasn't answered yet: `manifest bridge --doctor`.\n"
    )
    return 0


def check_voice(*, out: TextIO) -> int:
    """Load the natural voice in the foreground: the first time it downloads the model, so
    setup does that (not the first conversation), and any problem shows here."""
    problem = speech.supported()
    if problem:
        out.write(
            f"Natural voice: not on this computer ({problem}). Answers show as text; install it with: curl -fsSL https://manifeststartup.com/voice.sh | sh\n"
        )
        return 0
    out.write("Natural voice: loading Kokoro (the first time downloads about 330 MB)…\n")
    out.flush()
    voice = Voice(log=lambda line: (out.write(line + "\n"), out.flush()))
    return 0 if voice.load() else 1


def set_cartesia_key(*, out: TextIO) -> int:
    """Ask for a Cartesia API key (hidden), keep it in the Keychain, restart the bridge."""
    import getpass

    key = getpass.getpass("Cartesia API key (from play.cartesia.ai, input hidden): ").strip()
    if not key:
        out.write("No key entered; nothing changed.\n")
        return 1
    if not speech.save_cartesia_key(key):
        out.write("Couldn't save it in the Keychain.\n")
        return 1
    subprocess.run(
        ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LAUNCH_LABEL}"], capture_output=True
    )
    out.write(
        "Saved in your Keychain. Manifest voice now speaks with Cartesia (the voice from "
        "Pipecat's demos); the answers' text is sent to Cartesia to be spoken.\n"
    )
    return 0


def uninstall(*, out: TextIO) -> int:
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}/{LAUNCH_LABEL}"], capture_output=True
    )
    plist = launch_agent_path()
    if plist.exists():
        plist.unlink()
    out.write(
        "The Manifest bridge no longer starts at login (its saved settings stay in "
        f"{setup.settings_path()}, so reinstalling keeps your agents).\n"
    )
    return 0


def run(
    agent: LocalAgent | AgentPool,
    *,
    port: int,
    extra_origins: list[str],
    out: TextIO,
    voice: str | None = None,
) -> int:
    origins = DEFAULT_ORIGINS + tuple(o.rstrip("/") for o in extra_origins)
    try:
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(serve(agent, port=port, origins=origins, out=out, voice=voice))
    except BridgeError as exc:
        out.write(f"{exc}\n")
        return 1
    return 0
