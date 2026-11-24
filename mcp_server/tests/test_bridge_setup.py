"""Issue #132: connecting the person's own agents to Manifest voice, safely and seamlessly.

One saved source of truth, honest readiness, Codex's folder trust kept, several agents with
the one used last as the default, and switching that hands over the conversation.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from manifest_cli import agents, bridge
from manifest_cli import bridge_setup as setup
from manifest_cli.main import main

APP = "https://manifeststartup.com"


def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


# -- one source of truth ---------------------------------------------------------


def test_settings_round_trip_atomically_and_privately(tmp_path):
    settings = setup.BridgeSettings(
        default="codex",
        agents={
            "codex": setup.AgentProfile(workdir=str(tmp_path), continue_last=True, model="o4"),
            "claude": setup.AgentProfile(agent_args=["--permission-mode=plan"]),
        },
        origins=["https://self.example"],
        voice="af_heart",
    )
    path = setup.save(settings, tmp_path / "bridge.json")
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert not (tmp_path / "bridge.tmp").exists()
    assert setup.load(path) == settings


def test_saved_settings_never_carry_a_codex_trust_bypass(tmp_path):
    settings = setup.BridgeSettings(
        default="codex", agents={"codex": setup.AgentProfile(agent_args=["--skip-git-repo-check"])}
    )
    with pytest.raises(ValueError, match="skip-git-repo-check"):
        setup.save(settings, tmp_path / "b.json")


def test_an_older_login_item_keeps_its_agent_and_options():
    """The reported setup: `--agent codex` from home. Reinstalling keeps Codex, never
    swaps in Claude, keeps --continue, and drops a bypass flag."""
    old = ["--agent", "codex", "--port", "47821", "--continue", "--agent-arg=--skip-git-repo-check"]
    settings = setup.settings_from_args(old)
    assert settings.default == "codex" and list(settings.agents) == ["codex"]
    profile = settings.agents["codex"]
    assert profile.continue_last is True and profile.agent_args == []


def test_a_single_agent_file_migrates_without_changing_the_choice():
    settings = setup.BridgeSettings.from_dict(
        {"agent": "codex", "workdir": "/tmp/x", "port": 47821}
    )
    assert settings.default == "codex" and settings.agents["codex"].workdir == "/tmp/x"


def test_login_item_runs_from_the_saved_settings_in_the_agents_folder(tmp_path):
    plist = bridge.launch_agent_plist(
        ["--config", str(tmp_path / "bridge.json")],
        path_env="/usr/bin",
        log=tmp_path / "b.log",
        workdir=tmp_path,
    )
    assert plist["ProgramArguments"][-2:] == ["--config", str(tmp_path / "bridge.json")]
    assert plist["WorkingDirectory"] == str(tmp_path)


def test_install_saves_everything_and_the_login_item_reads_it(tmp_path, monkeypatch):
    repo = _repo(tmp_path / "app")
    saved = tmp_path / "bridge.json"
    monkeypatch.setenv("MANIFEST_BRIDGE_CONFIG", str(saved))
    monkeypatch.setattr(setup, "installed_args", lambda: None)
    monkeypatch.setattr(setup, "installed_agents", lambda: ["claude", "codex"])
    calls: list[tuple[list[str], dict]] = []
    monkeypatch.setattr(bridge, "install", lambda args, **kw: calls.append((args, kw)) or 0)
    out = io.StringIO()
    code = main(
        ["bridge", "--install", "--agent", "codex", "--workdir", str(repo), "--continue"],
        out=out,
        err=io.StringIO(),
        stdin=io.StringIO(),
    )
    assert code == 0
    settings = setup.load(saved)
    assert settings and settings.default == "codex"
    assert settings.agents["codex"].workdir == str(repo.resolve())
    assert settings.agents["codex"].continue_last is True
    assert "claude" in settings.agents  # set up too, ready to switch to
    args, kw = calls[0]
    assert args == ["--config", str(saved)] and kw["workdir"] == repo.resolve()


def test_foreground_bridge_without_options_runs_exactly_the_saved_settings(tmp_path, monkeypatch):
    saved = tmp_path / "bridge.json"
    setup.save(
        setup.BridgeSettings(default="codex", agents={"codex": setup.AgentProfile(workdir="/r")}),
        saved,
    )
    monkeypatch.setenv("MANIFEST_BRIDGE_CONFIG", str(saved))
    seen = {}

    def fake_run(pool, **kw):
        seen["pool"], seen["kw"] = pool, kw
        return 0

    monkeypatch.setattr(bridge, "run", fake_run)
    assert main(["bridge"], out=io.StringIO(), err=io.StringIO(), stdin=io.StringIO()) == 0
    assert seen["pool"].settings.default == "codex"
    assert seen["pool"].settings.agents["codex"].workdir == "/r"
    assert seen["pool"].save_to == saved  # a switch by voice is remembered


# -- Codex trust --------------------------------------------------------------------


def test_codex_never_bypasses_its_folder_check():
    agent = agents.make_agent("codex", cwd="/repo")
    for argv in (
        agent.command("hi")[0],
        agents.make_agent("codex", continue_last=True).command("hi")[0],
        agents.make_agent("codex", resume="t-1").command("hi")[0],
    ):
        assert "--skip-git-repo-check" not in argv
    assert agent.cwd == "/repo"


def test_codex_trusts_a_project_not_the_home_folder(tmp_path):
    assert setup.codex_trusts(_repo(tmp_path / "repo"))
    plain = tmp_path / "plain"
    plain.mkdir()
    assert not setup.codex_trusts(plain)


def test_an_untrusted_folder_is_a_clear_setup_step(tmp_path, monkeypatch):
    monkeypatch.setattr(setup.shutil, "which", lambda b: f"/bin/{b}")
    monkeypatch.setattr(setup, "agent_signed_in", lambda _k: True)
    problems = setup.check_agent("codex", setup.AgentProfile(workdir=str(tmp_path)))
    assert [p.code for p in problems] == [setup.TRUST_REQUIRED]
    assert "--workdir" in problems[0].fix and "skip" not in problems[0].fix
    explained = setup.explain_agent_error(
        "codex",
        "Not inside a trusted directory and --skip-git-repo-check was not specified.",
        tmp_path,
    )
    assert "doesn't trust this folder" in explained and "--workdir" in explained


def test_missing_agent_and_sign_in_are_specific(monkeypatch, tmp_path):
    monkeypatch.setattr(setup.shutil, "which", lambda _b: None)
    assert setup.check_agent("codex", setup.AgentProfile())[0].code == setup.AGENT_MISSING
    monkeypatch.setattr(setup.shutil, "which", lambda b: f"/bin/{b}")
    monkeypatch.setattr(setup, "agent_signed_in", lambda _k: False)
    problems = setup.check_agent("claude", setup.AgentProfile(workdir=str(tmp_path)))
    assert problems[0].code == setup.AUTH_NEEDED and "claude auth login" in problems[0].fix


# -- the agent used last, and switching ------------------------------------------


def _session(path: Path, cwd: str, when: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "session_meta", "payload": {"cwd": cwd}}) + "\n")
    os.utime(path, (when, when))


def test_the_default_agent_is_the_one_used_last(tmp_path, monkeypatch):
    monkeypatch.setattr(setup.shutil, "which", lambda b: f"/bin/{b}")
    now = time.time()
    _session(tmp_path / ".claude/projects/-x/a.jsonl", "/x", now - 600)
    _session(tmp_path / ".codex/sessions/2026/11/23/rollout-1.jsonl", "/repo", now - 5)
    assert setup.active_agent(["claude", "codex"], home=tmp_path) == "codex"
    assert setup.last_session("codex", home=tmp_path)[1] == "/repo"
    os.utime(tmp_path / ".claude/projects/-x/a.jsonl", (now, now))
    assert setup.active_agent(["claude", "codex"], home=tmp_path) == "claude"


def test_switch_requests():
    assert bridge.switch_request("Switch to Codex") == "codex"
    assert bridge.switch_request("okay, go back to Claude Code please") == "claude"
    assert bridge.switch_request("use codex instead") == "codex"
    assert bridge.switch_request("what did codex change in the repo?") is None


class _Echo(agents.LocalAgent):
    """A fake agent that repeats what it was asked."""

    def __init__(self, name: str):
        super().__init__(name=name)
        self.prompts: list[str] = []

    async def turn(self, prompt: str):
        self.prompts.append(prompt)
        yield ("say", f"{self.name} heard it.")


async def _request(port: int, raw: bytes) -> tuple[str, bytes]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw)
    await writer.drain()
    data = await reader.read()
    writer.close()
    head, _, body = data.partition(b"\r\n\r\n")
    return head.decode().split("\r\n")[0], body


def _post(path: str, body: dict) -> bytes:
    data = json.dumps(body).encode()
    return (
        f"POST {path} HTTP/1.1\r\nOrigin: {APP}\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(data)}\r\n\r\n"
    ).encode() + data


def _pool(default: str = "claude", **problems) -> bridge.AgentPool:
    settings = setup.BridgeSettings(
        default=default,
        agents={"claude": setup.AgentProfile(), "codex": setup.AgentProfile(workdir="/repo")},
    )
    pool = bridge.AgentPool(settings)
    pool.live = {"claude": _Echo("Claude Code"), "codex": _Echo("Codex")}
    pool.problems = {"claude": [], "codex": problems.get("codex", [])}
    pool.check = lambda **_k: None  # type: ignore[method-assign]
    return pool


def _said(body: bytes) -> list[str]:
    return [json.loads(line)["text"] for line in body.decode().splitlines() if line]


def test_switching_by_voice_hands_the_new_agent_the_conversation():
    pool = _pool()

    async def run():
        b = bridge.Bridge(pool, origins=bridge.DEFAULT_ORIGINS, out=io.StringIO())
        server = await asyncio.start_server(b.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            first = await _request(port, _post("/turn", {"text": "plan the launch email"}))
            switched = await _request(port, _post("/turn", {"text": "switch to Codex"}))
            after = await _request(port, _post("/turn", {"text": "now write it"}))
            health = await _request(port, f"GET /health HTTP/1.1\r\nOrigin: {APP}\r\n\r\n".encode())
        return first, switched, after, json.loads(health[1])

    first, switched, after, health = asyncio.run(run())
    assert _said(first[1])[0] == "Claude Code heard it."
    assert "talking to Codex now" in _said(switched[1])[0]
    assert _said(after[1])[0] == "Codex heard it."
    handed = pool.live["codex"].prompts[0]
    assert "plan the launch email" in handed and "Claude Code heard it." in handed
    assert handed.rstrip().endswith("now write it")
    assert pool.live["codex"].prompts == [handed]  # the handoff goes once
    assert health["agent_id"] == "codex" and health["ready"] is True
    assert {a["id"] for a in health["agents"]} == {"claude", "codex"}


def test_switching_back_keeps_each_agents_own_session():
    pool = _pool()
    pool.select("codex")
    codex = pool.agent()
    pool.select("claude")
    pool.select("codex")
    assert pool.agent() is codex  # same process/session, not a new one


def test_an_explicit_agent_that_isnt_ready_says_why_and_never_falls_back():
    trust = setup.Problem(setup.TRUST_REQUIRED, "Codex won't answer in ~.", "Choose a project.")
    pool = _pool(default="codex", codex=[trust])

    async def run():
        b = bridge.Bridge(pool, origins=bridge.DEFAULT_ORIGINS, out=io.StringIO())
        server = await asyncio.start_server(b.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            turn = await _request(port, _post("/turn", {"text": "hello"}))
            health = await _request(port, f"GET /health HTTP/1.1\r\nOrigin: {APP}\r\n\r\n".encode())
        return turn, json.loads(health[1])

    turn, health = asyncio.run(run())
    events = [json.loads(line) for line in turn[1].decode().splitlines()]
    assert events[0]["kind"] == "error" and "Choose a project" in events[0]["text"]
    assert pool.live["claude"].prompts == [] and pool.live["codex"].prompts == []
    assert health["ready"] is False and health["problems"][0]["code"] == setup.TRUST_REQUIRED


def test_active_default_skips_an_agent_that_cant_answer(monkeypatch):
    trust = setup.Problem(setup.TRUST_REQUIRED, "x", "y")
    pool = _pool(default=setup.ACTIVE, codex=[trust])
    monkeypatch.setattr(setup, "active_agent", lambda ready, home=None: ready[0] if ready else None)
    assert pool.resolve() == "claude"


def test_the_app_can_switch_agents(tmp_path):
    pool = _pool()
    pool.save_to = tmp_path / "bridge.json"

    async def run():
        b = bridge.Bridge(pool, origins=bridge.DEFAULT_ORIGINS, out=io.StringIO())
        server = await asyncio.start_server(b.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            return await _request(port, _post("/agent", {"agent": "codex"}))

    status, body = asyncio.run(run())
    assert status.endswith("200 OK") and json.loads(body)["agent_id"] == "codex"
    assert setup.load(pool.save_to).default == "codex"  # remembered after a restart


def test_a_port_in_use_says_what_holds_it(monkeypatch):
    monkeypatch.setattr(setup, "bridge_health", lambda *_a, **_k: {"agent": "Codex"})
    assert "already running" in bridge.port_in_use(47821)
    assert "manifest bridge --use" in bridge.port_in_use(47821)
    monkeypatch.setattr(setup, "bridge_health", lambda *_a, **_k: None)
    assert "another program" in bridge.port_in_use(47821)


@pytest.mark.skipif(sys.platform == "win32", reason="posix shell")
def test_probe_runs_a_real_turn_through_the_same_agent_command(tmp_path):
    ok = setup.probe(
        f"{sys.executable} -c \"print('OK')\"", setup.AgentProfile(workdir=str(tmp_path))
    )
    assert ok is None
    failed = setup.probe(
        f"{sys.executable} -c \"import sys; sys.stderr.write('Not inside a trusted directory'); sys.exit(1)\"",
        setup.AgentProfile(workdir=str(tmp_path)),
    )
    assert failed and failed.code == setup.LAUNCH_FAILED
