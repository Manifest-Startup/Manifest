"""Local agents that can be the brain of `manifest voice --agent`.

Manifest's voice server listens and speaks (relay mode); the agent the person already uses
answers each turn here, on their computer, with its own tools, permissions and history:

    claude   Claude Code (`claude -p`). Sessions are shared with the Claude Code VS Code
             extension, so `--continue` picks up the newest conversation in this folder.
    codex    OpenAI Codex CLI (`codex exec`).
    <cmd>    any command: the turn arrives on stdin, whatever it prints is spoken.

Each agent yields ("say", text) for words to speak and ("tool", name) for activity.
An agent's own end-of-turn event ends the turn at once: Claude Code, for example, runs the
person's Stop hooks after answering, which can take seconds, so the process finishes them
in the background while the next turn is already being heard.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

VOICE_STYLE = (
    "You are being spoken to out loud through Manifest voice; your replies are read aloud. "
    "Answer in short, natural spoken sentences. No markdown, lists, code blocks, tables, "
    "URLs or file paths read aloud: say what you did or found in plain words. Before a long "
    "task, say in one short sentence what you are about to do."
)

# Read-only by default; the Manifest plugin's own tools ask for confirmation themselves.
CLAUDE_DEFAULT_TOOLS = "mcp__plugin_manifest_manifest Read Grep Glob WebSearch WebFetch"

Event = tuple[str, str]


async def _drain(process: asyncio.subprocess.Process) -> None:
    """Let a finished turn's process run its remaining hooks without blocking anyone."""
    if process.stdout:
        async for _ in process.stdout:
            pass
    await process.wait()


def _short(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class LocalAgent:
    """Base: run one turn as a subprocess and stream its events."""

    name: str
    extra_args: list[str] = field(default_factory=list)
    resume: str | None = None
    continue_last: bool = False
    session_id: str | None = None
    process: asyncio.subprocess.Process | None = None
    _finishing: set[asyncio.Future[None]] = field(default_factory=set)

    def command(self, prompt: str) -> tuple[list[str], bytes | None]:  # pragma: no cover
        raise NotImplementedError

    def parse(self, line: str) -> list[Event]:  # pragma: no cover
        raise NotImplementedError

    def finish(self, output: str) -> list[Event]:
        return []

    async def turn(self, prompt: str) -> AsyncIterator[Event]:
        argv, stdin = self.command(prompt)
        self.process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=16 * 1024 * 1024,
        )
        process = self.process
        if stdin is not None and process.stdin:
            process.stdin.write(stdin)
            await process.stdin.drain()
            process.stdin.close()
        lines: list[str] = []
        assert process.stdout
        async for raw in process.stdout:
            line = raw.decode(errors="replace").rstrip("\n")
            lines.append(line)
            events = self.parse(line)
            for event in events:
                if event[0] != "done":
                    yield event
            if any(kind == "done" for kind, _ in events):
                self.process = None
                self._finishing.add(asyncio.ensure_future(_drain(process)))
                return
        for event in self.finish("\n".join(lines)):
            yield event
        code = await process.wait()
        self.process = None
        if code not in (0, None):
            err = (await process.stderr.read()).decode(errors="replace") if process.stderr else ""
            last = err.strip().splitlines()[-1] if err.strip() else f"exit code {code}"
            yield ("error", _short(last, 160))

    def stop(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()


@dataclass
class ClaudeCodeAgent(LocalAgent):
    """One long-lived Claude Code process for the whole conversation.

    `claude -p --input-format stream-json` takes one user message per line, so MCP servers
    and hooks start once (it can take many seconds) instead of on every turn, and it is
    started as the conversation connects, while the person is still talking.
    """

    name: str = "Claude Code"
    _late_result: bool = False

    def command(self, prompt: str = "") -> tuple[list[str], bytes | None]:
        argv = ["claude", "-p", "--input-format", "stream-json"]
        argv += ["--output-format", "stream-json", "--verbose"]
        argv += ["--append-system-prompt", VOICE_STYLE]
        if not any(
            a.startswith(
                ("--allowedTools", "--allowed-tools", "--permission-mode", "--dangerously")
            )
            for a in self.extra_args
        ):
            argv += ["--allowedTools", CLAUDE_DEFAULT_TOOLS]
        if self.session_id:
            argv += ["--resume", self.session_id]
        elif self.resume:
            argv += ["--resume", self.resume]
        elif self.continue_last:
            argv += ["--continue"]
        argv += self.extra_args
        return argv, None

    @staticmethod
    def message(prompt: str) -> bytes:
        body = {"type": "user", "message": {"role": "user", "content": prompt}}
        return (json.dumps(body) + "\n").encode()

    async def start(self) -> None:
        if self.process and self.process.returncode is None:
            return
        argv, _ = self.command()
        self._late_result = False
        self.process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=16 * 1024 * 1024,
        )

    async def turn(self, prompt: str) -> AsyncIterator[Event]:
        await self.start()
        process = self.process
        assert process and process.stdin and process.stdout
        process.stdin.write(self.message(prompt))
        await process.stdin.drain()
        async for raw in process.stdout:
            events = self.parse(raw.decode(errors="replace"))
            for event in events:
                if event[0] != "done":
                    yield event
            if any(kind == "done" for kind, _ in events):
                return
        # The process ended (crashed or was stopped): start fresh, resuming, next turn.
        self.process = None
        yield ("error", "Claude Code stopped")

    def parse(self, line: str) -> list[Event]:
        try:
            event = json.loads(line)
        except ValueError:
            return []
        if event.get("session_id"):
            self.session_id = event["session_id"]
        kind = event.get("type")
        events: list[Event] = []
        if kind == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "text" and str(block.get("text", "")).strip():
                    events.append(("say", block["text"].strip()))
                elif block.get("type") == "tool_use":
                    events.append(("tool", str(block.get("name") or "tool")))
        elif _stop_hook_started(event):
            # The answer is complete; the person's Stop hooks can take a while. End the turn
            # now and skip the result line that follows them.
            self._late_result = True
            events.append(("done", ""))
        elif kind == "result":
            if self._late_result:
                self._late_result = False
                return []
            if event.get("is_error"):
                events.append(
                    ("error", _short(str(event.get("result") or "Claude Code failed"), 160))
                )
            events.append(("done", ""))
        return events

    def stop(self) -> None:
        process = self.process
        if process and process.returncode is None:
            if process.stdin:
                process.stdin.close()  # let it finish its hooks and save the session
            asyncio.get_event_loop().call_later(10, _kill, process)


def _stop_hook_started(event: dict) -> bool:
    if event.get("type") == "system" and event.get("subtype") == "hook_started":
        return str(event.get("hook_event") or "") == "Stop"
    return event.get("type") == "tool_progress" and event.get("tool_name") == "Stop"


def _kill(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        process.terminate()


@dataclass
class CodexAgent(LocalAgent):
    name: str = "Codex"

    def command(self, prompt: str) -> tuple[list[str], bytes | None]:
        text = f"{VOICE_STYLE}\n\n{prompt}" if not self.session_id else prompt
        if self.session_id:
            argv = ["codex", "exec", "resume", "--json", *self.extra_args, self.session_id, "-"]
        elif self.resume:
            argv = ["codex", "exec", "resume", "--json", *self.extra_args, self.resume, "-"]
        elif self.continue_last:
            argv = ["codex", "exec", "resume", "--json", "--last", *self.extra_args, "-"]
        else:
            argv = ["codex", "exec", "--json", "--skip-git-repo-check", *self.extra_args, "-"]
        return argv, text.encode()

    def parse(self, line: str) -> list[Event]:
        try:
            event = json.loads(line)
        except ValueError:
            return []
        if event.get("type") == "thread.started" and event.get("thread_id"):
            self.session_id = event["thread_id"]
        item = event.get("item") or {}
        if event.get("type") == "item.completed":
            kind = item.get("type")
            if kind == "agent_message" and str(item.get("text", "")).strip():
                return [("say", item["text"].strip())]
            if kind in ("command_execution", "mcp_tool_call", "file_change", "web_search"):
                label = item.get("tool") or item.get("command") or kind.replace("_", " ")
                return [("tool", _short(str(label)))]
        if event.get("type") in ("turn.failed", "error"):
            message = (
                (event.get("error") or {}).get("message") or event.get("message") or "Codex failed"
            )
            return [("error", _short(str(message), 160))]
        if event.get("type") == "turn.completed":
            return [("done", "")]
        return []


@dataclass
class CommandAgent(LocalAgent):
    """Any command: the turn on stdin, its whole output spoken."""

    shell_command: str = ""

    def command(self, prompt: str) -> tuple[list[str], bytes | None]:
        return [*shlex.split(self.shell_command), *self.extra_args], prompt.encode()

    def parse(self, line: str) -> list[Event]:
        return []

    def finish(self, output: str) -> list[Event]:
        return [("say", output.strip())] if output.strip() else []


def make_agent(
    spec: str,
    *,
    extra_args: list[str] | None = None,
    resume: str | None = None,
    continue_last: bool = False,
) -> LocalAgent:
    """`claude`, `codex`, or a command line."""
    common = {
        "extra_args": list(extra_args or []),
        "resume": resume,
        "continue_last": continue_last,
    }
    key = spec.strip().lower()
    if key in ("claude", "claude-code", "claude_code"):
        return ClaudeCodeAgent(**common)
    if key == "codex":
        return CodexAgent(**common)
    words = shlex.split(spec)
    return CommandAgent(name=words[0] if words else "agent", shell_command=spec, **common)


def missing_agent(agent: LocalAgent) -> str | None:
    binary = {"Claude Code": "claude", "Codex": "codex"}.get(agent.name)
    if isinstance(agent, CommandAgent):
        words = shlex.split(agent.shell_command)
        binary = words[0] if words else None
    if binary and not shutil.which(binary):
        return f"`{binary}` isn't on your PATH. Install it, or pass another --agent."
    return None
