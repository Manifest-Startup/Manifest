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

    GET  /health   {"ok": true, "agent": "Claude Code", "voice": ws url | null, "interrupt": true}
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
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from manifest_cli import speech
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
        named = f' "{title}"' if title else ""
        return f"(In the Manifest app, the person is looking at the idea{named}, id {idea}.)"
    return f"(In the Manifest app, the person is on {path}.)" if path else ""


class Bridge:
    def __init__(
        self,
        agent: LocalAgent,
        *,
        origins: tuple[str, ...],
        out: TextIO,
        voice_url: str | None = None,
        speech: Voice | None = None,
        speech_problem: str | None = None,
    ) -> None:
        self.agent, self.origins, self.out = agent, origins, out
        self.voice_url = voice_url  # the local Pipecat voice, when it runs here
        self.speech = speech  # Kokoro on the Apple GPU, for /speak
        # Why there's no natural voice on a Mac that could have one (a reinstall without the
        # natural-voice extra, issue #108); None when it's off on purpose or not possible.
        self.speech_problem = speech_problem
        self.lock = asyncio.Lock()

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
            body = json.dumps(
                {
                    "ok": True,
                    "agent": self.agent.name,
                    "voice": self.voice_url,
                    "interrupt": True,  # a hung-up /turn stops the agent's answer
                    # The natural voice (POST /speak), once its model has loaded.
                    "speech": self.speech.voice if self.speech and self.speech.ready else None,
                    # "ready", "loading", or what's wrong; the app upgrades once it's ready.
                    "speech_status": getattr(self.speech, "status", "ready")
                    if self.speech
                    else (self.speech_problem or "off"),
                }
            ).encode()
            send("200 OK", [*cors, "Content-Type: application/json"], body)
        elif path in ("/vault/folder", "/vault/sync") and method in ("GET", "POST"):
            length = int(headers.get("content-length") or 0)
            status, body = await (
                self._vault_sync(method)
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
        prompt = " ".join(p for p in (describe_context(payload.get("context")), text) if p)
        self.out.write(f"you  {text}\n")
        self.out.flush()
        async with self.lock:  # one turn at a time, in order
            watcher = asyncio.ensure_future(link.watch())
            try:
                async for kind, value in self.agent.turn(prompt):
                    if kind in ("say", "tool", "error") and not link.gone:
                        await emit(kind, value)
                        if kind == "say":
                            self.out.write(f"{self.agent.name.lower()}  {value}\n")
                            self.out.flush()
            except FileNotFoundError:
                await emit("error", f"Could not start {self.agent.name}.")
            finally:
                watcher.cancel()
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
    agent: LocalAgent,
    *,
    port: int = DEFAULT_PORT,
    origins: tuple[str, ...] = DEFAULT_ORIGINS,
    out: TextIO,
    voice: str | None = None,
) -> None:
    from manifest_cli import local_voice

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
        agent,
        origins=origins,
        out=out,
        voice_url=voice_url,
        speech=spoken,
        speech_problem=f"natural voice not installed: {no_speech}" if fixable else None,
    )
    server = await asyncio.start_server(bridge.handle, "127.0.0.1", port)
    # HTTPS too, for Safari (it won't call http://127.0.0.1 from a secure page).
    from manifest_cli import bridge_tls

    tls = bridge_tls.server_context()
    secure = (
        await asyncio.start_server(bridge.handle, "127.0.0.1", bridge_tls.HTTPS_PORT, ssl=tls)
        if tls
        else None
    )
    warm = getattr(agent, "start", None)
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
    out.write(
        f"Manifest can now talk to {agent.name} on this computer (http://127.0.0.1:{port}).\n"
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
        + "Open Manifest and tap the voice button; no OpenAI key needed. Ctrl-C to stop.\n"
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
            agent.stop()


LAUNCH_LABEL = "com.manifeststartup.bridge"


def launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_LABEL}.plist"


def launch_agent_plist(
    args: list[str], *, path_env: str, log: Path, launcher: Path | None = None
) -> dict[str, Any]:
    """A login item that keeps `manifest bridge` running (restarted if it stops). With a
    `launcher` (macos_app), it runs as "Manifest Bridge", which may use an iCloud vault."""
    program = ([str(launcher)] if launcher else []) + [sys.executable]
    return {
        "Label": LAUNCH_LABEL,
        "ProgramArguments": [*program, "-m", "manifest_cli", "bridge", *args],
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(Path.home()),
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


def install(args: list[str], *, out: TextIO) -> int:
    """Run the bridge at login (macOS LaunchAgent), replacing an earlier install."""
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
            launch_agent_plist(args, path_env=os.environ.get("PATH", ""), log=log, launcher=app),
            handle,
        )
    started = _bootstrap_when_unloaded(domain, plist)
    if started.returncode != 0:
        out.write(f"Could not start it: {started.stderr.strip() or started.returncode}\n")
        return 1
    out.write(
        "The Manifest bridge now starts when you log in and stays running.\n"
        f"Voice in Manifest talks to your agent with no key. Log: {log}\n"
        "Undo with: manifest bridge --uninstall\n"
    )
    return 0


def check_voice(*, out: TextIO) -> int:
    """Load the natural voice in the foreground: the first time it downloads the model, so
    setup does that (not the first conversation), and any problem shows here."""
    problem = speech.supported()
    if problem:
        out.write(f"Natural voice: not on this computer ({problem}). The browser's voice speaks.\n")
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
    out.write("The Manifest bridge no longer starts at login.\n")
    return 0


def run(
    agent: LocalAgent, *, port: int, extra_origins: list[str], out: TextIO, voice: str | None = None
) -> int:
    origins = DEFAULT_ORIGINS + tuple(o.rstrip("/") for o in extra_origins)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve(agent, port=port, origins=origins, out=out, voice=voice))
    return 0
