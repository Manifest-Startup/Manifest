"""One source of truth for `manifest bridge`: saved settings and honest readiness checks.

The foreground bridge, the macOS login item and the app all read the same saved settings
(``~/.config/manifest/bridge.json``, mode 0600), so installing, restarting or upgrading never
drops the agents, folders, sessions or voice the person chose (issue #132).

Several agents can be set up at once (Claude Code and Codex). By default the bridge answers
with the one the person used most recently on this computer ("active"), and they can switch
at any time by voice, in the app or with `manifest bridge --use codex`.

Readiness separates "the bridge is listening" from "the agent can answer". Each problem has a
stable code, a plain message and the next step. Nothing here edits an agent's own settings:
Codex decides which folders it trusts, and the bridge never passes ``--skip-git-repo-check``.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
KNOWN_AGENTS = {"claude": "Claude Code", "codex": "Codex"}
ACTIVE = "active"  # the agent used most recently on this computer

# Problem codes (stable: the app and support refer to them).
AGENT_MISSING = "agent_missing"
AUTH_NEEDED = "auth_needed"
WORKDIR_MISSING = "workdir_missing"
TRUST_REQUIRED = "trust_required"
PORT_IN_USE = "port_in_use"
SERVICE_OUTDATED = "service_outdated"
NO_AGENT = "no_agent"
LAUNCH_FAILED = "launch_failed"
MANIFEST_NOT_CONNECTED = "manifest_not_connected"


def settings_path() -> Path:
    explicit = os.environ.get("MANIFEST_BRIDGE_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "manifest" / "bridge.json"


def agent_key(spec: str) -> str:
    """claude, codex, active, or a command line (as given)."""
    key = spec.strip().lower()
    if key in ("", "auto", ACTIVE, "default"):
        return ACTIVE
    if key in ("claude-code", "claude_code", "claude code"):
        return "claude"
    return key if key in KNOWN_AGENTS else spec.strip()


def agent_name(key: str) -> str:
    return KNOWN_AGENTS.get(key) or (shlex.split(key) or ["agent"])[0]


@dataclass
class AgentProfile:
    """How one agent runs for voice: its folder, model, session and approved options."""

    workdir: str = ""  # "" → home
    model: str | None = None
    continue_last: bool = False
    resume: str | None = None
    agent_args: list[str] = field(default_factory=list)

    @property
    def folder(self) -> Path:
        return Path(self.workdir).expanduser() if self.workdir else Path.home()

    def validate(self) -> None:
        if self.workdir and not Path(self.workdir).expanduser().is_absolute():
            raise ValueError("The agent's folder must be a full path.")
        if any("skip-git-repo-check" in a for a in self.agent_args):
            # Codex's own folder check is the person's security boundary; never saved.
            raise ValueError(
                "--skip-git-repo-check isn't allowed: choose a project folder Codex trusts."
            )


@dataclass
class BridgeSettings:
    default: str = ACTIVE  # "active", or one key of `agents`
    agents: dict[str, AgentProfile] = field(default_factory=dict)
    port: int = 47821
    origins: list[str] = field(default_factory=list)
    voice: str | None = None
    version: int = SCHEMA_VERSION

    def validate(self) -> None:
        if not 1024 <= int(self.port) <= 65535:
            raise ValueError("The port must be between 1024 and 65535.")
        if self.default != ACTIVE and self.default not in self.agents:
            raise ValueError(f"{agent_name(self.default)} isn't set up; add it with --agent.")
        for profile in self.agents.values():
            profile.validate()

    def profile(self, key: str) -> AgentProfile:
        return self.agents.setdefault(key, AgentProfile())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BridgeSettings:
        if "agents" not in data and "agent" in data:  # a single-agent file: same choice
            key = agent_key(str(data["agent"]))
            fields = {k: data[k] for k in AgentProfile.__dataclass_fields__ if k in data}
            data = {**data, "default": key, "agents": {} if key == ACTIVE else {key: fields}}
        agents = {
            str(k): AgentProfile(**{f: v[f] for f in AgentProfile.__dataclass_fields__ if f in v})
            for k, v in (data.get("agents") or {}).items()
            if isinstance(v, dict)
        }
        settings = cls(
            default=agent_key(str(data.get("default") or ACTIVE)),
            agents=agents,
            port=int(data.get("port") or 47821),
            origins=[str(o) for o in data.get("origins") or []],
            voice=data.get("voice"),
        )
        settings.validate()
        return settings


def load(path: Path | None = None) -> BridgeSettings | None:
    path = path or settings_path()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return BridgeSettings.from_dict(data)
    except (TypeError, ValueError):
        return None


def save(settings: BridgeSettings, path: Path | None = None) -> Path:
    settings.validate()
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(asdict(settings), handle, indent=2)
        handle.write("\n")
    os.replace(tmp, path)  # atomic: a crash never leaves half a file
    return path


# -- which agent is the person using right now? ----------------------------------


def _latest_dir(folder: Path) -> Path | None:
    try:
        names = sorted((p for p in folder.iterdir() if p.is_dir()), key=lambda p: p.name)
    except OSError:
        return None
    return names[-1] if names else None


def _session_files(key: str, home: Path) -> list[Path]:
    if key == "claude":
        projects = home / ".claude" / "projects"
        try:
            return [f for d in projects.iterdir() if d.is_dir() for f in d.glob("*.jsonl")]
        except OSError:
            return []
    if key == "codex":
        files: list[Path] = []
        year = _latest_dir(home / ".codex" / "sessions")
        for month in sorted(year.iterdir())[-2:] if year and year.is_dir() else []:
            for day in sorted(p for p in month.iterdir() if p.is_dir())[-3:]:
                files += list(day.glob("*.jsonl"))
        return files
    return []


def _session_head(path: Path) -> tuple[str | None, bool]:
    """(the session's folder, whether the person worked in it themselves). Voice's own
    sessions (Manifest's bridge, scripted `claude -p`, `codex exec`) don't count: the
    agent "you used last" is the one you were working in, not the voice itself."""
    folder, mine = None, True
    try:
        with path.open() as handle:
            for _, line in zip(range(40), handle, strict=False):
                event = json.loads(line)
                payload = event.get("payload") or {}
                if event.get("type") == "session_meta" and (
                    payload.get("originator") == "manifest-voice" or payload.get("source") == "exec"
                ):
                    mine = False
                if event.get("entrypoint") == "sdk-cli":
                    mine = False
                cwd = event.get("cwd") or payload.get("cwd")
                if isinstance(cwd, str) and cwd and folder is None:
                    folder = cwd
                if folder and (event.get("entrypoint") or event.get("type") == "session_meta"):
                    break
    except (OSError, ValueError):
        pass
    return folder, mine


def last_session(key: str, home: Path | None = None) -> tuple[float, str | None] | None:
    """(when, folder) of the newest session the person worked in with this agent, or None.

    Only file times and each session's first lines (its folder and who started it) are
    read, never the conversation itself."""
    home = home or Path.home()
    dated = []
    for path in _session_files(key, home):
        try:
            dated.append((path.stat().st_mtime, path))
        except OSError:
            continue
    for when, path in sorted(dated, reverse=True)[:40]:
        folder, mine = _session_head(path)
        if mine:
            return when, folder
    return None


def active_agent(candidates: list[str], home: Path | None = None) -> str | None:
    """Of these agents, the one used most recently here (installed ones only)."""
    best, best_time = None, -1.0
    for key in candidates:
        if key not in KNOWN_AGENTS or not shutil.which(key):
            continue
        seen = last_session(key, home)
        when = seen[0] if seen else 0.0
        if when > best_time:
            best, best_time = key, when
    return best


def installed_agents() -> list[str]:
    return [key for key in KNOWN_AGENTS if shutil.which(key)]


def suggested_folder(key: str) -> str:
    """A folder that works for this agent: Codex's newest project if Codex trusts it."""
    if key != "codex":
        return ""
    seen = last_session("codex")
    for candidate in ([seen[1]] if seen and seen[1] else []) + [os.getcwd()]:
        root = git_root(Path(candidate))
        if root:
            return str(root)
    return ""


# -- readiness -------------------------------------------------------------------


@dataclass
class Problem:
    code: str
    message: str
    fix: str
    blocking: bool = True

    def public(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "fix": self.fix}


def git_root(folder: Path) -> Path | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(folder), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            # Judge the folder itself: an inherited GIT_DIR (git hooks set it) would make
            # any folder look like that repository.
            env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip() else None


def codex_trusts(folder: Path) -> bool:
    """Whether `codex exec` will run in this folder without bypassing its check.

    Measured with codex-cli 0.172 (2026-11-23): `codex exec` and `codex exec resume` run only
    inside a Git repository; a `trust_level = "trusted"` entry alone isn't enough, and
    outside one they fail with "Not inside a trusted directory".
    """
    return git_root(folder) is not None


def trust_fix(folder: Path) -> str:
    return (
        "Choose a project folder (a Git repository) for Codex: "
        'manifest bridge --install --agent codex --workdir "/path/to/project". '
        f"Codex only answers inside a project it trusts, and {folder} isn't one. "
        "If Codex asks to trust it, accept in Codex itself (run `codex` there once)."
    )


def _run(argv: list[str], timeout: float = 15) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def agent_version(key: str) -> str | None:
    if key not in KNOWN_AGENTS:
        return None
    done = _run([key, "--version"], timeout=10)
    if not done or done.returncode:
        return None
    return (done.stdout.strip().splitlines() or [""])[0][:80] or None


def agent_signed_in(key: str) -> bool | None:
    """True/False when the agent can say; None when it can't be told (then don't block)."""
    if key == "codex":
        done = _run(["codex", "login", "status"])
        return None if done is None else done.returncode == 0
    if key == "claude":
        done = _run(["claude", "auth", "status"])
        if done is None:
            return None
        try:
            return bool(json.loads(done.stdout).get("loggedIn"))
        except (ValueError, AttributeError):
            return None if done.returncode == 0 else False
    return None


def check_agent(key: str, profile: AgentProfile, *, auth: bool = True) -> list[Problem]:
    """Can this agent answer a turn from its folder? (Fast; runs no model.)"""
    words = [key] if key in KNOWN_AGENTS else shlex.split(key)
    binary = words[0] if words else key
    name = agent_name(key)
    if not shutil.which(binary):
        install = {
            "claude": "Install Claude Code (https://claude.com/claude-code)",
            "codex": "Install Codex (https://developers.openai.com/codex)",
        }.get(key, f"Install `{binary}`")
        return [
            Problem(
                AGENT_MISSING,
                f"{name} isn't installed on this computer (no `{binary}` on PATH).",
                f"{install}, or choose another agent.",
            )
        ]
    folder = profile.folder
    if not folder.is_dir():
        return [
            Problem(
                WORKDIR_MISSING,
                f"The folder for {name} doesn't exist: {folder}.",
                "Choose an existing folder with --workdir.",
            )
        ]
    problems: list[Problem] = []
    if key == "codex" and not codex_trusts(folder):
        problems.append(
            Problem(
                TRUST_REQUIRED,
                f"Codex won't answer in {folder}: it isn't a project Codex trusts.",
                trust_fix(folder),
            )
        )
    if auth and agent_signed_in(key) is False:
        login = {"claude": "claude auth login", "codex": "codex login"}[key]
        problems.append(
            Problem(
                AUTH_NEEDED,
                f"{name} isn't signed in.",
                f"Run `{login}` once, then `manifest bridge --restart`.",
            )
        )
    if (
        auth
        and key == "codex"
        and not _cli_signed_in()
        and codex_manifest_auth() == "not_logged_in"
    ):
        problems.append(
            Problem(
                MANIFEST_NOT_CONNECTED,
                "Codex isn't signed in to Manifest, so voice can talk but can't open or change "
                "your ideas, notes or feedback.",
                "Run `manifest login` once (or `codex mcp login manifest`).",
                blocking=False,  # the conversation still works
            )
        )
    return problems


def _cli_signed_in() -> bool:
    """Signed in to the Manifest CLI: the bridge then gives every agent Manifest's tools."""
    try:
        from manifest_cli import config

        return bool(config.token())
    except Exception:
        return False


def codex_manifest_auth() -> str | None:
    """Codex's sign-in to the Manifest MCP server ("not_logged_in", "oauth", …), or None
    when Codex has no Manifest server or can't say. Reads only Codex's own status."""
    done = _run(["codex", "mcp", "list", "--json"], timeout=10)
    if not done or done.returncode:
        return None
    try:
        servers = json.loads(done.stdout)
    except ValueError:
        return None
    for server in servers if isinstance(servers, list) else []:
        url = str(((server.get("transport") or {}).get("url")) or "")
        if server.get("name") == "manifest" or "manifeststartup.com/mcp" in url:
            if not server.get("enabled", True):
                return "disabled"
            return str(server.get("auth_status") or "") or None
    return None


def explain_agent_error(key: str, text: str, folder: Path) -> str:
    """A known launch error in plain words with the next step; otherwise the error as is."""
    lowered = text.lower()
    if key == "codex" and "trusted directory" in lowered:
        return f"Codex doesn't trust this folder. {trust_fix(folder)}"
    if any(s in lowered for s in ("not logged in", "please run /login", "login required")):
        login = {"claude": "claude auth login", "codex": "codex login"}.get(key, "its login")
        return f"{agent_name(key)} isn't signed in: run `{login}` once."
    return text


def probe(key: str, profile: AgentProfile, *, timeout: float = 120) -> Problem | None:
    """A real, harmless first turn through the same agent command the bridge uses."""
    import asyncio

    from manifest_cli.agents import make_agent

    agent = make_agent(
        key, extra_args=profile.agent_args, model=profile.model, cwd=str(profile.folder)
    )

    async def one_turn() -> tuple[list[str], list[str]]:
        said: list[str] = []
        errors: list[str] = []
        try:
            async for kind, value in agent.turn("Manifest setup check: reply with just OK."):
                if kind == "say":
                    said.append(value)
                elif kind == "error":
                    errors.append(value)
        finally:
            agent.stop()
        return said, errors

    try:
        said, errors = asyncio.run(asyncio.wait_for(one_turn(), timeout))
    except (TimeoutError, OSError) as exc:
        said, errors = [], [str(exc) or "no answer in time"]
    if said and not errors:
        return None
    detail = explain_agent_error(key, errors[-1] if errors else "no answer", profile.folder)
    return Problem(
        LAUNCH_FAILED,
        f"{agent_name(key)} didn't answer the test turn: {detail}",
        "Fix that, then run `manifest bridge --doctor --probe` again.",
    )


def bridge_health(port: int, timeout: float = 2.0) -> dict[str, Any] | None:
    """The running bridge's /health (asked as the Manifest app), or None."""
    import http.client

    from manifest_cli.bridge import DEFAULT_ORIGINS

    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        conn.request("GET", "/health", headers={"Origin": DEFAULT_ORIGINS[0]})
        response = conn.getresponse()
        body = response.read()
        conn.close()
        data = json.loads(body) if response.status == 200 else None
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def tell_bridge(port: int, key: str, timeout: float = 5.0) -> dict[str, Any] | None:
    """Switch the running bridge to this agent now (no restart); None if it isn't running."""
    import http.client

    from manifest_cli.bridge import DEFAULT_ORIGINS

    body = json.dumps({"agent": key})
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        conn.request(
            "POST",
            "/agent",
            body=body,
            headers={"Origin": DEFAULT_ORIGINS[0], "Content-Type": "application/json"},
        )
        response = conn.getresponse()
        data = json.loads(response.read() or b"{}")
        conn.close()
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def installed_args() -> list[str] | None:
    """The `manifest bridge` options the macOS login item runs with, or None."""
    import plistlib

    from manifest_cli.bridge import launch_agent_path

    try:
        with launch_agent_path().open("rb") as handle:
            program = plistlib.load(handle).get("ProgramArguments") or []
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None
    if "bridge" not in program:
        return None
    return [str(a) for a in program[program.index("bridge") + 1 :]]


_VALUED = {
    "--agent",
    "--port",
    "--resume",
    "--workdir",
    "--model",
    "--voice",
    "--origin",
    "--agent-arg",
}


def settings_from_args(args: list[str]) -> BridgeSettings:
    """Read an older login item's options, so reinstalling keeps exactly the same choice."""
    values: dict[str, Any] = {"agent_args": [], "origins": []}
    i = 0
    while i < len(args):
        name, eq, value = args[i].partition("=")
        if not eq and name in _VALUED and i + 1 < len(args):
            value, i = args[i + 1], i + 1
        if name == "--agent-arg":
            if "skip-git-repo-check" not in value:
                values["agent_args"].append(value)
        elif name == "--origin":
            values["origins"].append(value)
        elif name == "--continue":
            values["continue_last"] = True
        elif name in _VALUED:
            values[name[2:]] = value
        i += 1
    key = agent_key(str(values.get("agent") or ACTIVE))
    settings = BridgeSettings(
        default=key,
        port=int(values.get("port") or 47821),
        origins=values["origins"],
        voice=values.get("voice"),
    )
    profile = AgentProfile(
        workdir=str(values.get("workdir") or ""),
        model=values.get("model"),
        continue_last=bool(values.get("continue_last")),
        resume=values.get("resume"),
        agent_args=values["agent_args"],
    )
    for target in [key] if key != ACTIVE else installed_agents():
        settings.agents[target] = AgentProfile(**asdict(profile))
    return settings


def uses_saved_settings(args: list[str] | None) -> bool:
    return bool(args) and any(a == "--config" or a.startswith("--config=") for a in args or [])


def doctor(settings: BridgeSettings, *, run_probe: bool = False) -> list[tuple[str, str, str]]:
    """Every check as (status, name, detail): status is ok, warn or fail."""
    from manifest_cli import bridge_tls, speech

    rows: list[tuple[str, str, str]] = []
    if not settings.agents:
        rows.append(("fail", NO_AGENT, "No agent is set up. Run `manifest bridge --install`."))
    for key, profile in settings.agents.items():
        version = agent_version(key)
        problems = check_agent(key, profile)
        label = agent_name(key) + (f" {version}" if version else "")
        blocking = [p for p in problems if p.blocking]
        rows.append(("fail" if blocking else "ok", label, f"in {profile.folder}"))
        for problem in problems:
            status = "fail" if problem.blocking else "warn"
            rows.append((status, problem.code, f"{problem.message} {problem.fix}"))
        if run_probe and not blocking:
            failed = probe(key, profile)
            rows.append(
                ("fail", failed.code, failed.message)
                if failed
                else ("ok", "Test turn", f"{agent_name(key)} answered.")
            )
    if settings.default == ACTIVE:
        now = active_agent(list(settings.agents))
        rows.append(
            ("ok", "Answers with", f"the agent you used last ({agent_name(now)})" if now else "?")
        )
    else:
        rows.append(("ok", "Answers with", agent_name(settings.default)))
    health = bridge_health(settings.port)
    if health is None:
        rows.append(
            ("warn", "Bridge", f"not running on port {settings.port}: `manifest bridge --install`")
        )
    else:
        ready = health.get("ready", True)
        rows.append(
            (
                "ok" if ready else "fail",
                "Bridge",
                f"running with {health.get('agent') or '?'}"
                + ("" if ready else ", not ready: see above, then `manifest bridge --restart`"),
            )
        )
    args = installed_args()
    if args is not None and not uses_saved_settings(args):
        rows.append(
            (
                "warn",
                SERVICE_OUTDATED,
                "The login item was set up by an older version. Run `manifest bridge --install` "
                "once (it keeps your agent and folder).",
            )
        )
    tls = bridge_tls.certificate_ok()
    rows.append(
        (
            "ok" if tls else "warn",
            "Safari (HTTPS)",
            "ready" if tls else "not set up: `manifest bridge --install`; Chrome works without it",
        )
    )
    no_speech = speech.supported() if settings.voice != "browser" else "browser voice chosen"
    rows.append(
        (
            "ok" if not no_speech else "warn",
            "Natural voice",
            "available" if not no_speech else str(no_speech),
        )
    )
    rows.append(("ok", "Microphone", "your browser asks the first time you tap voice"))
    return rows
