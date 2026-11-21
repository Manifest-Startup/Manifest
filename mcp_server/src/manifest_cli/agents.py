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
import contextlib
import json
import shlex
import shutil
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

VOICE_STYLE = (
    "You are being spoken to out loud through Manifest voice; your replies are read aloud. "
    "Answer in short, natural spoken sentences. No markdown, lists, code blocks, tables, "
    "URLs or file paths read aloud: say what you did or found in plain words. Before a long "
    "task, say in one short sentence what you are about to do. "
    "The person's Manifest vault is a folder on this computer. To say where it is, run "
    "`manifest vault-folder`; to move it when they ask (for example to iCloud Drive), run "
    "`manifest vault-folder icloud`, `documents`, `home` or a full path. Moving keeps every "
    "file and restarts sync. "
    "Their own GitHub is in the Manifest github_* tools (repositories, issues, pull requests, "
    "branches, files, Actions, releases). If it isn't connected, run `manifest github connect` "
    "(it reuses the GitHub CLI's login); never ask them to read a token aloud."
)

# Read-only by default; the Manifest plugin's own tools ask for confirmation themselves. The one
# shell commands allowed are showing or moving the vault folder (it never deletes anything) and
# connecting GitHub from the GitHub CLI's login (the token never passes through the agent).
CLAUDE_DEFAULT_TOOLS = (
    "mcp__plugin_manifest_manifest Read Grep Glob WebSearch WebFetch Bash(manifest vault-folder:*) "
    "Bash(manifest github connect) Bash(manifest github status) Bash(manifest github)"
)

Event = tuple[str, str]

# Voice must answer fast: Claude Code's Haiku starts speaking ~0.6 s sooner than the default
# model (measured warm, 2026-11-20). `--model default` keeps the person's own choice.
CLAUDE_VOICE_MODEL = "haiku"


def _has_flag(args: list[str], *names: str) -> bool:
    return any(a == n or a.startswith(n + "=") for a in args for n in names)


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
    model: str | None = None  # None: the agent's fast voice default; "default": its own
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

    async def interrupt(self) -> None:
        """Stop the answer in progress (the person talked over it)."""
        if self.process and self.process.returncode is None:
            self.process.terminate()

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
    # Words stream in as Claude writes; each sentence is passed on as soon as it ends,
    # so speech starts while the rest of the answer is still being written.
    _pending: str = ""
    _streamed: bool = False

    def command(self, prompt: str = "") -> tuple[list[str], bytes | None]:
        argv = ["claude", "-p", "--input-format", "stream-json"]
        argv += ["--output-format", "stream-json", "--verbose", "--include-partial-messages"]
        argv += ["--append-system-prompt", VOICE_STYLE]
        if not any(
            a.startswith(
                ("--allowedTools", "--allowed-tools", "--permission-mode", "--dangerously")
            )
            for a in self.extra_args
        ):
            argv += ["--allowedTools", CLAUDE_DEFAULT_TOOLS]
        if not _has_flag(self.extra_args, "--model") and self.model != "default":
            argv += ["--model", self.model or CLAUDE_VOICE_MODEL]
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

    async def interrupt(self) -> None:
        """Ask Claude Code to stop the current answer; the turn then ends within ~1 s and the
        same process takes the next question (no restart, the session stays warm)."""
        process = self.process
        if not (process and process.returncode is None and process.stdin):
            return
        body = {"type": "control_request", "request_id": f"stop-{time.monotonic_ns()}"}
        body["request"] = {"subtype": "interrupt"}
        process.stdin.write((json.dumps(body) + "\n").encode())
        with contextlib.suppress(ConnectionError):
            await process.stdin.drain()

    def parse(self, line: str) -> list[Event]:
        try:
            event = json.loads(line)
        except ValueError:
            return []
        if event.get("session_id"):
            self.session_id = event["session_id"]
        kind = event.get("type")
        events: list[Event] = []
        if kind == "stream_event":
            return self._stream(event.get("event") or {})
        if kind == "assistant":
            return self._assistant(event.get("message") or {})
        if _stop_hook_started(event):
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

    def _assistant(self, message: dict) -> list[Event]:
        events: list[Event] = []
        for block in message.get("content") or []:
            if block.get("type") == "text" and str(block.get("text", "")).strip():
                if not self._streamed:  # already spoken sentence by sentence
                    events.append(("say", block["text"].strip()))
            elif block.get("type") == "tool_use":
                events.append(("tool", str(block.get("name") or "tool")))
        return events

    def _stream(self, event: dict) -> list[Event]:
        kind = event.get("type")
        if kind == "message_start":
            self._pending, self._streamed = "", False
            return []
        delta = event.get("delta") or {}
        if kind == "content_block_delta" and delta.get("type") == "text_delta":
            self._streamed = True
            self._pending += str(delta.get("text") or "")
            sentences, self._pending = split_sentences(self._pending)
            return [("say", s) for s in sentences]
        if kind in ("content_block_stop", "message_stop") and self._pending.strip():
            rest, self._pending = self._pending.strip(), ""
            return [("say", rest)]
        return []

    def stop(self) -> None:
        process = self.process
        if process and process.returncode is None:
            if process.stdin:
                process.stdin.close()  # let it finish its hooks and save the session
            asyncio.get_event_loop().call_later(10, _kill, process)


def split_sentences(text: str) -> tuple[list[str], str]:
    """Complete sentences in `text` (ended by . ! ? and a space), and the unfinished rest."""
    out: list[str] = []
    start = 0
    for i, char in enumerate(text):
        if char in ".!?" and i + 1 < len(text) and text[i + 1].isspace():
            sentence = text[start : i + 1].strip()
            # "e.g. " and "3.5 " are not sentence ends.
            if sentence and not sentence.lower().endswith(
                ("e.g.", "i.e.", "etc.", "vs.", "mr.", "dr.")
            ):
                out.append(sentence)
                start = i + 1
    return out, text[start:]


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
        fast: list[str] = []
        if self.model not in (None, "default"):
            fast = ["-m", self.model]
        if self.model != "default" and "model_reasoning_effort" not in " ".join(self.extra_args):
            fast += ["-c", 'model_reasoning_effort="low"']  # spoken answers: start talking sooner
        if self.session_id:
            argv = [
                "codex",
                "exec",
                "resume",
                "--json",
                *fast,
                *self.extra_args,
                self.session_id,
                "-",
            ]
        elif self.resume:
            argv = ["codex", "exec", "resume", "--json", *fast, *self.extra_args, self.resume, "-"]
        elif self.continue_last:
            argv = ["codex", "exec", "resume", "--json", "--last", *fast, *self.extra_args, "-"]
        else:
            argv = [
                "codex",
                "exec",
                "--json",
                "--skip-git-repo-check",
                *fast,
                *self.extra_args,
                "-",
            ]
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


def detect_agent() -> str:
    """The agent to use when none is named: Claude Code if installed, else Codex."""
    for binary in ("claude", "codex"):
        if shutil.which(binary):
            return binary
    return "claude"


def make_agent(
    spec: str,
    *,
    extra_args: list[str] | None = None,
    resume: str | None = None,
    continue_last: bool = False,
    model: str | None = None,
) -> LocalAgent:
    """`auto` (Claude Code, else Codex), `claude`, `codex`, or a command line."""
    common = {
        "extra_args": list(extra_args or []),
        "resume": resume,
        "continue_last": continue_last,
        "model": model,
    }
    key = spec.strip().lower()
    if key in ("", "auto"):
        key = detect_agent()
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
