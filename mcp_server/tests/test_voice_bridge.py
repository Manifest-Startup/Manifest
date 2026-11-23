"""`manifest bridge`: the Manifest app reaches the person's own agent on 127.0.0.1."""

from __future__ import annotations

import asyncio
import io
import json
import sys

import pytest
from manifest_cli import agents, bridge

APP = "https://manifeststartup.com"


async def _request(port: int, raw: bytes) -> tuple[str, dict[str, str], bytes]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw)
    await writer.drain()
    data = await reader.read()
    writer.close()
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.decode().split("\r\n")
    headers = {k.lower(): v.strip() for k, _, v in (h.partition(":") for h in lines[1:])}
    return lines[0], headers, body


def _post(path: str, body: dict, origin: str = APP) -> bytes:
    data = json.dumps(body).encode()
    return (
        f"POST {path} HTTP/1.1\r\nHost: x\r\nOrigin: {origin}\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(data)}\r\n\r\n"
    ).encode() + data


def test_bridge_answers_the_app_with_the_agent_and_refuses_other_sites():
    script = "import sys; print('agent heard: ' + sys.stdin.read())"
    agent = agents.make_agent(f'{sys.executable} -c "{script}"')
    out = io.StringIO()

    async def run():
        b = bridge.Bridge(agent, origins=bridge.DEFAULT_ORIGINS, out=out)
        server = await asyncio.start_server(b.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            health = await _request(port, f"GET /health HTTP/1.1\r\nOrigin: {APP}\r\n\r\n".encode())
            pre = await _request(
                port,
                f"OPTIONS /turn HTTP/1.1\r\nOrigin: {APP}\r\n"
                "Access-Control-Request-Private-Network: true\r\n\r\n".encode(),
            )
            turn = await _request(
                port,
                _post(
                    "/turn",
                    {"text": "list my ideas", "context": {"idea_id": "i1", "idea_title": "Solar"}},
                ),
            )
            evil = await _request(
                port, _post("/turn", {"text": "rm -rf"}, origin="https://evil.example")
            )
        return health, pre, turn, evil

    health, pre, turn, evil = asyncio.run(run())
    assert json.loads(health[2])["ok"] is True
    assert health[1]["access-control-allow-origin"] == APP
    assert (
        pre[0].endswith("204 No Content")
        and pre[1]["access-control-allow-private-network"] == "true"
    )
    events = [json.loads(line) for line in turn[2].decode().splitlines()]
    assert events[-1] == {"kind": "done", "text": ""}
    said = events[0]["text"]
    assert said.startswith("agent heard: (In the Manifest app") and said.endswith("list my ideas")
    assert '"Solar"' in said
    assert evil[0].endswith("403 Forbidden") and b"Only the Manifest app" in evil[2]
    assert "you  list my ideas" in out.getvalue()


def test_context_line():
    assert (
        bridge.describe_context({"path": "/ideas"})
        == "(In the Manifest app, the person is on /ideas.)"
    )
    assert bridge.describe_context(None) == ""


def test_install_writes_a_login_item_that_keeps_the_bridge_running(tmp_path):
    plist = bridge.launch_agent_plist(
        ["--agent", "claude", "--port", "47821"],
        path_env="/usr/bin:/opt/homebrew/bin",
        log=tmp_path / "b.log",
    )
    assert plist["ProgramArguments"][1:] == [
        "-m",
        "manifest_cli",
        "bridge",
        "--agent",
        "claude",
        "--port",
        "47821",
    ]
    assert plist["RunAtLoad"] and plist["KeepAlive"]
    assert plist["EnvironmentVariables"]["PATH"].endswith("homebrew/bin")


def test_local_voice_helpers():
    from manifest_cli import local_voice

    assert (
        local_voice.last_user_text(
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "x"},
                {"role": "user", "content": [{"type": "text", "text": "open it"}]},
            ]
        )
        == "open it"
    )
    assert local_voice.context_line({"idea_id": "a1", "idea_title": "Solar"}) == (
        '(In the Manifest app, the person is looking at the idea "Solar", id a1.)'
    )
    assert local_voice.context_line(None) == ""


def test_install_retries_until_the_old_bridge_has_stopped(tmp_path, monkeypatch):
    """`bootstrap` fails with error 5 while the old bridge is still exiting."""
    import subprocess

    calls: list[str] = []
    bootstrap_results = iter([5, 5, 0])

    def fake_run(cmd, **_kwargs):
        calls.append(cmd[1])
        code = {"bootout": 0, "print": 1}.get(cmd[1])
        if code is None:
            code = next(bootstrap_results)
        stderr = "Bootstrap failed: 5: Input/output error" if code else ""
        return subprocess.CompletedProcess(cmd, code, "", stderr)

    monkeypatch.setattr(bridge.sys, "platform", "darwin")
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    monkeypatch.setattr(bridge.time, "sleep", lambda _s: None)
    monkeypatch.setattr(bridge, "launch_agent_path", lambda: tmp_path / "agent.plist")
    monkeypatch.setattr(bridge.Path, "home", staticmethod(lambda: tmp_path))
    from manifest_cli import macos_app

    monkeypatch.setattr(macos_app, "launcher", lambda *a, **k: None)
    from manifest_cli import bridge_tls

    monkeypatch.setattr(bridge_tls, "ensure", lambda **_k: True)  # no real keychain in tests
    out = io.StringIO()
    assert bridge.install(["--agent", "claude"], out=out) == 0
    assert calls.count("bootstrap") == 3
    assert "starts when you log in" in out.getvalue()


def test_bridge_shows_and_moves_the_vault_folder(monkeypatch):
    from manifest_cli import vault_folder

    moves = []
    monkeypatch.setattr(vault_folder, "where", lambda: {"folder": "/v", "icloud": False})

    def move(place):
        if place == "nowhere":
            raise vault_folder.VaultFolderError("Give the new place as a full path.")
        moves.append(place)
        return {"folder": "/icloud/v", "moved": True}

    monkeypatch.setattr(vault_folder, "move", move)
    out = io.StringIO()

    async def run():
        b = bridge.Bridge(agents.make_agent("cat"), origins=bridge.DEFAULT_ORIGINS, out=out)
        server = await asyncio.start_server(b.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            get = await _request(
                port, f"GET /vault/folder HTTP/1.1\r\nOrigin: {APP}\r\n\r\n".encode()
            )
            ok = await _request(port, _post("/vault/folder", {"place": "icloud"}))
            bad = await _request(port, _post("/vault/folder", {"place": "nowhere"}))
            evil = await _request(
                port, _post("/vault/folder", {"place": "/tmp"}, origin="https://evil.example")
            )
        return get, ok, bad, evil

    get, ok, bad, evil = asyncio.run(run())
    assert json.loads(get[2]) == {"folder": "/v", "icloud": False}
    assert get[1]["access-control-allow-origin"] == APP
    assert json.loads(ok[2])["moved"] is True and moves == ["icloud"]
    assert bad[0].endswith("409 Conflict") and "full path" in json.loads(bad[2])["error"]
    assert evil[0].endswith("403 Forbidden")


def test_vault_folder_runs_the_newest_script_with_move(tmp_path, monkeypatch):
    from manifest_cli import vault_folder

    old = tmp_path / "old.py"
    old.write_text("print('no move here')")
    new = tmp_path / "new.py"
    new.write_text(
        "import json, sys\ndef cmd_move(): pass\nprint(json.dumps({'args': sys.argv[1:]}))\n"
    )
    monkeypatch.setattr(vault_folder, "_candidates", lambda: [old, new])
    assert vault_folder.move("icloud") == {"args": ["move", "icloud", "--json"]}
    assert vault_folder.where() == {"args": ["where", "--json"]}
    with pytest.raises(vault_folder.VaultFolderError):
        vault_folder.move("  ")
    monkeypatch.setattr(vault_folder, "_candidates", lambda: [old])
    with pytest.raises(vault_folder.VaultFolderError, match="isn't set up"):
        vault_folder.where()


def test_bridge_runs_through_its_app_so_it_may_use_an_icloud_vault(tmp_path):
    exe = tmp_path / "Manifest Bridge.app/Contents/MacOS/bridge"
    plist = bridge.launch_agent_plist([], path_env="", log=tmp_path / "b.log", launcher=exe)
    assert plist["ProgramArguments"][:2] == [str(exe), sys.executable]


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS app bundle")
def test_macos_app_is_built_once_and_signed(tmp_path):
    from manifest_cli import macos_app

    exe = macos_app.launcher("Manifest Bridge", "com.manifeststartup.bridge", base=tmp_path)
    assert exe == tmp_path / "Manifest Bridge.app/Contents/MacOS/bridge"
    info = (tmp_path / "Manifest Bridge.app/Contents/Info.plist").read_text()
    assert "<string>com.manifeststartup.bridge</string>" in info
    before = exe.stat().st_mtime_ns
    assert macos_app.launcher("Manifest Bridge", "com.manifeststartup.bridge", base=tmp_path) == exe
    assert exe.stat().st_mtime_ns == before  # kept, so a permission granted to it lasts
    import subprocess

    out = subprocess.run([str(exe), "echo", "ran"], capture_output=True, text=True)
    assert out.stdout.strip() == "ran"


def test_hanging_up_a_turn_interrupts_the_agent():
    class Slow(agents.LocalAgent):
        interrupted = 0

        async def turn(self, prompt):
            for i in range(200):
                yield ("say", f"Sentence {i}. " + "x" * 2000)
                await asyncio.sleep(0.01)

        async def interrupt(self):
            Slow.interrupted += 1

    agent = Slow(name="Slow")
    out = io.StringIO()

    async def run():
        b = bridge.Bridge(agent, origins=bridge.DEFAULT_ORIGINS, out=out)
        server = await asyncio.start_server(b.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(_post("/turn", {"text": "tell me everything"}))
            await writer.drain()
            await reader.readuntil(b"Sentence 1.")
            writer.transport.abort()  # the person talked over it
            for _ in range(200):
                if Slow.interrupted:
                    break
                await asyncio.sleep(0.02)

    asyncio.run(run())
    assert Slow.interrupted >= 1 and "(interrupted)" in out.getvalue()


def test_local_speech_models_only_on_a_computer_with_room(monkeypatch):
    from manifest_cli import local_voice

    monkeypatch.setattr(
        local_voice.os, "sysconf", lambda n: 4096 if n == "SC_PAGE_SIZE" else 2 * 1024**2
    )
    assert not local_voice.enough_memory()  # 8 GB
    monkeypatch.setattr(
        local_voice.os, "sysconf", lambda n: 4096 if n == "SC_PAGE_SIZE" else 4 * 1024**2
    )
    assert local_voice.enough_memory()  # 16 GB


def test_bridge_speaks_a_sentence_in_the_natural_voice():
    class FakeVoice:
        voice, ready, warmed, status = "af_heart", True, 0, "ready"

        async def speak(self, text):
            return b"\x01\x00" * len(text)

        def warm(self):
            FakeVoice.warmed += 1

    agent = agents.make_agent("claude")

    async def run():
        b = bridge.Bridge(
            agent, origins=bridge.DEFAULT_ORIGINS, out=io.StringIO(), speech=FakeVoice()
        )
        server = await asyncio.start_server(b.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            health = await _request(port, f"GET /health HTTP/1.1\r\nOrigin: {APP}\r\n\r\n".encode())
            spoken = await _request(port, _post("/speak", {"text": "Hello there."}))
            warm = await _request(port, _post("/speak/warm", {}))
            evil = await _request(
                port, _post("/speak", {"text": "hi"}, origin="https://evil.example")
            )
        return health, spoken, warm, evil

    health, spoken, warm, evil = asyncio.run(run())
    assert json.loads(health[2])["speech"] == "af_heart"
    assert spoken[0].endswith("200 OK") and spoken[1]["x-sample-rate"] == "24000"
    assert spoken[2] == b"\x01\x00" * len("Hello there.")
    assert warm[0].endswith("204 No Content") and FakeVoice.warmed == 1
    assert evil[0].endswith("403 Forbidden")


def test_natural_voice_only_where_it_can_run(monkeypatch):
    from manifest_cli import speech

    monkeypatch.setattr(speech.platform, "system", lambda: "Linux")
    assert "Apple silicon" in (speech.supported() or "")
    voice = speech.Voice()
    assert asyncio.run(voice.speak("Not loaded yet.")) == b""  # the app keeps the browser voice


def test_bridge_certificate_is_limited_to_this_mac_and_keeps_no_signing_key(tmp_path):
    from manifest_cli import bridge_tls

    bridge_tls.make_certificate(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bridge.key", "bridge.pem", "ca.pem"]
    assert bridge_tls.certificate_ok(tmp_path)
    assert bridge_tls.server_context(tmp_path) is not None
    import subprocess

    text = subprocess.run(
        ["openssl", "x509", "-in", str(tmp_path / "ca.pem"), "-noout", "-text"],
        capture_output=True,
        text=True,
    ).stdout
    assert "Name Constraints" in text and "127.0.0.1" in text


def test_cartesia_speaks_in_pipecats_voice_and_falls_back_to_kokoro():
    import httpx
    from manifest_cli import speech

    seen: list[httpx.Request] = []
    status = {"code": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status["code"], content=b"\x02\x00" * 4)

    class Kokoro:
        ready, voice = True, "af_heart"

        async def speak(self, text):
            return b"kokoro"

        def warm(self):
            pass

    voice = speech.CartesiaVoice("sk_car_test", fallback=Kokoro())
    voice._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert asyncio.run(voice.speak("Hello  there.")) == b"\x02\x00" * 4
    request = seen[0]
    assert str(request.url) == "https://api.cartesia.ai/tts/bytes"
    assert request.headers["authorization"] == "Bearer sk_car_test"
    assert request.headers["cartesia-version"] == speech.CARTESIA_VERSION
    body = json.loads(request.content)
    assert body["voice"] == {"id": speech.PIPECAT_VOICE} and body["transcript"] == "Hello there."
    assert body["output_format"] == {
        "container": "raw",
        "encoding": "pcm_s16le",
        "sample_rate": 24000,
    }

    status["code"] = 401  # a bad key or no credit: Kokoro says it instead
    assert asyncio.run(voice.speak("Again.")) == b"kokoro"
    assert "401" in (voice.problem or "")


def test_cartesia_key_comes_from_the_environment_first(monkeypatch):
    from manifest_cli import speech

    monkeypatch.setenv("CARTESIA_API_KEY", " sk_car_env ")
    assert speech.cartesia_key() == "sk_car_env"


def test_a_voice_that_fails_to_load_says_why_and_never_exits(monkeypatch):
    from manifest_cli import speech

    lines: list[str] = []
    voice = speech.Voice(log=lines.append)
    monkeypatch.setattr(speech, "text_model_problem", lambda: None)

    utils = pytest.importorskip("mlx_audio.tts.utils")  # Apple silicon extra

    def exits(_model):
        raise SystemExit(2)  # what misaki does when its download fails

    monkeypatch.setattr(utils, "load_model", exits)
    assert voice.load() is False  # no SystemExit escapes
    assert voice.status.startswith("SystemExit") and "unavailable" in lines[-1]

    monkeypatch.setattr(speech, "text_model_problem", lambda: "the English text model is missing")
    assert voice.load() is False and "text model" in voice.status


def test_bridge_sets_what_a_deleted_note_does_in_the_vault(monkeypatch):
    from manifest_cli import vault_folder

    chosen = []

    def set_on_delete(mode):
        chosen.append(mode)
        return {"folder": "/v", "on_delete": mode}

    monkeypatch.setattr(vault_folder, "set_on_delete", set_on_delete)
    monkeypatch.setattr(vault_folder, "move", lambda place: pytest.fail("must not move"))

    async def run():
        b = bridge.Bridge(
            agents.make_agent("cat"), origins=bridge.DEFAULT_ORIGINS, out=io.StringIO()
        )
        server = await asyncio.start_server(b.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            return await _request(port, _post("/vault/folder", {"on_delete": "keep"}))

    status, _, body = asyncio.run(run())
    assert status.endswith("200 OK") and json.loads(body)["on_delete"] == "keep"
    assert chosen == ["keep"]


def test_set_on_delete_checks_the_choice(tmp_path, monkeypatch):
    from manifest_cli import vault_folder

    script = tmp_path / "s.py"
    script.write_text(
        "import json, sys\ndef cmd_move(): pass\nprint(json.dumps({'args': sys.argv[1:]}))\n"
    )
    monkeypatch.setattr(vault_folder, "_candidates", lambda: [script])
    assert vault_folder.set_on_delete("Keep") == {"args": ["where", "--json"]}
    with pytest.raises(vault_folder.VaultFolderError):
        vault_folder.set_on_delete("shred")


def test_bridge_syncs_the_vault_now_for_pull_to_refresh(monkeypatch):
    from manifest_cli import vault_folder

    calls = []
    monkeypatch.setattr(
        vault_folder, "sync_now", lambda: calls.append(1) or {"ok": True, "report": []}
    )

    async def run():
        b = bridge.Bridge(
            agents.make_agent("cat"), origins=bridge.DEFAULT_ORIGINS, out=io.StringIO()
        )
        server = await asyncio.start_server(b.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            ok = await _request(port, _post("/vault/sync", {}))
            evil = await _request(port, _post("/vault/sync", {}, origin="https://evil.example"))
        return ok, evil

    ok, evil = asyncio.run(run())
    assert ok[0].endswith("200 OK") and json.loads(ok[2])["ok"] is True
    assert evil[0].endswith("403 Forbidden") and calls == [1]


def test_sync_now_reports_offline_without_failing(tmp_path, monkeypatch):
    from manifest_cli import vault_folder

    script = tmp_path / "s.py"
    script.write_text("import sys\ndef cmd_move(): pass\nprint('offline')\nsys.exit(3)\n")
    monkeypatch.setattr(vault_folder, "_candidates", lambda: [script])
    assert vault_folder.sync_now()["offline"] is True
