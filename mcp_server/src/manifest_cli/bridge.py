"""`manifest bridge`: let the Manifest web app talk to the agent on this computer.

    Manifest web app / installed Chrome app ── http://127.0.0.1:47821 ──▶ Claude Code / Codex

Voice in the app needs no OpenAI key this way: the browser listens and speaks with its own
speech recognition and voices, and each turn goes to the agent you already use (with its
own tools, permissions and history), through this small local server.

Safety: it listens on 127.0.0.1 only and answers only pages from Manifest's own origins
(browsers send an Origin header that web pages cannot fake), so other websites cannot
drive your agent. The agent keeps its own permission rules (Claude Code is read-only by
default here; see ``agents.py``).

    GET  /health   {"ok": true, "agent": "Claude Code"}
    POST /turn     {"text": "...", "context": {"path", "idea_id", "idea_title"}}
                   → newline-delimited JSON: {"kind": "say"|"tool"|"error", "text"}…
                     then {"kind": "done"}
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any, TextIO

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
    def __init__(self, agent: LocalAgent, *, origins: tuple[str, ...], out: TextIO) -> None:
        self.agent, self.origins, self.out = agent, origins, out
        self.lock = asyncio.Lock()

    def _cors(self, origin: str) -> list[str]:
        return [
            f"Access-Control-Allow-Origin: {origin}",
            "Vary: Origin",
            "Access-Control-Allow-Methods: GET, POST, OPTIONS",
            "Access-Control-Allow-Headers: content-type",
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
            body = json.dumps({"ok": True, "agent": self.agent.name}).encode()
            send("200 OK", [*cors, "Content-Type: application/json"], body)
        elif method == "POST" and path == "/turn":
            length = int(headers.get("content-length") or 0)
            if length <= 0 or length > MAX_BODY:
                send("413 Payload Too Large", cors)
            else:
                payload = json.loads(await reader.readexactly(length))
                await self._turn(writer, cors, payload if isinstance(payload, dict) else {})
                return
        else:
            send("404 Not Found", cors)
        await writer.drain()

    async def _turn(self, writer: asyncio.StreamWriter, cors: list[str], payload: dict) -> None:
        text = " ".join(str(payload.get("text") or "").split())[:4000]
        head = [
            "HTTP/1.1 200 OK",
            *cors,
            "Content-Type: application/x-ndjson",
            "Cache-Control: no-store",
            "Connection: close",
        ]
        writer.write(("\r\n".join(head) + "\r\n\r\n").encode())

        async def emit(kind: str, value: str = "") -> None:
            writer.write((json.dumps({"kind": kind, "text": value}) + "\n").encode())
            await writer.drain()

        if not text:
            await emit("done")
            return
        prompt = " ".join(p for p in (describe_context(payload.get("context")), text) if p)
        self.out.write(f"you  {text}\n")
        self.out.flush()
        async with self.lock:  # one turn at a time, in order
            try:
                async for kind, value in self.agent.turn(prompt):
                    if kind in ("say", "tool", "error"):
                        await emit(kind, value)
                        if kind == "say":
                            self.out.write(f"{self.agent.name.lower()}  {value}\n")
                            self.out.flush()
            except FileNotFoundError:
                await emit("error", f"Could not start {self.agent.name}.")
        await emit("done")


async def serve(
    agent: LocalAgent,
    *,
    port: int = DEFAULT_PORT,
    origins: tuple[str, ...] = DEFAULT_ORIGINS,
    out: TextIO,
) -> None:
    bridge = Bridge(agent, origins=origins, out=out)
    server = await asyncio.start_server(bridge.handle, "127.0.0.1", port)
    warm = getattr(agent, "start", None)
    if warm is not None:
        await warm()  # Claude Code: start once now, so the first turn is quick
    out.write(
        f"Manifest can now talk to {agent.name} on this computer (http://127.0.0.1:{port}).\n"
        "Open Manifest and tap the voice button; no OpenAI key needed. Ctrl-C to stop.\n"
    )
    out.flush()
    async with server:
        try:
            await server.serve_forever()
        finally:
            agent.stop()


def run(agent: LocalAgent, *, port: int, extra_origins: list[str], out: TextIO) -> int:
    origins = DEFAULT_ORIGINS + tuple(o.rstrip("/") for o in extra_origins)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve(agent, port=port, origins=origins, out=out))
    return 0
