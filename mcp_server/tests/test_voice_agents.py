"""`manifest voice --agent`: the person's own agent answers, Manifest listens and speaks."""

from __future__ import annotations

import asyncio
import io
import json
import sys

from manifest_cli import agents, voice


def test_claude_code_command_resumes_its_session_and_stays_read_only_by_default():
    agent = agents.make_agent("claude", continue_last=True)
    argv, _ = agent.command()
    assert argv[:4] == ["claude", "-p", "--input-format", "stream-json"]
    assert "--continue" in argv
    assert json.loads(agent.message("what changed today?")) == {
        "type": "user",
        "message": {"role": "user", "content": "what changed today?"},
    }
    assert argv[argv.index("--allowedTools") + 1] == agents.CLAUDE_DEFAULT_TOOLS
    assert "spoken aloud" in argv[argv.index("--append-system-prompt") + 1]

    events = agent.parse(json.dumps({"type": "system", "subtype": "init", "session_id": "s-1"}))
    events += agent.parse(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Let me look."},
                        {"type": "tool_use", "name": "mcp__plugin_manifest_manifest__ideas"},
                    ]
                },
            }
        )
    )
    assert events == [("say", "Let me look."), ("tool", "mcp__plugin_manifest_manifest__ideas")]
    argv, _ = agent.command("and now?")
    assert argv[argv.index("--resume") + 1] == "s-1" and "--continue" not in argv

    # The answer is complete when the Stop hooks start; the late result line is skipped.
    assert agent.parse(
        json.dumps({"type": "system", "subtype": "hook_started", "hook_event": "Stop"})
    ) == [("done", "")]
    assert agent.parse(json.dumps({"type": "result", "session_id": "s-1"})) == []
    assert agent.parse(json.dumps({"type": "result", "session_id": "s-1"})) == [("done", "")]

    own = agents.make_agent("claude", extra_args=["--permission-mode", "acceptEdits"])
    assert "--allowedTools" not in own.command("x")[0]


def test_codex_command_and_events():
    agent = agents.make_agent("codex")
    argv, stdin = agent.command("hi")
    assert argv[:3] == ["codex", "exec", "--json"] and argv[-1] == "-"
    assert stdin.endswith(b"hi\n" + agents.VOICE_TURN_HINT.encode()) and b"spoken aloud" in stdin
    agent.parse(json.dumps({"type": "thread.started", "thread_id": "t-9"}))
    said = agent.parse(
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Done."}})
    )
    assert said == [("say", "Done.")]
    assert agent.command("again")[0][:4] == ["codex", "exec", "resume", "--json"]
    assert "t-9" in agent.command("again")[0]


def test_any_command_reads_stdin_and_its_output_is_spoken():
    script = "import sys; print('echo: ' + sys.stdin.read().upper())"
    agent = agents.make_agent(f'{sys.executable} -c "{script}"')

    async def run():
        return [event async for event in agent.turn("hello")]

    assert asyncio.run(run()) == [("say", "echo: HELLO")]


def test_missing_agent_is_explained():
    assert "isn't on your PATH" in agents.missing_agent(agents.make_agent("no-such-agent-xyz"))


class FakeAgent(agents.LocalAgent):
    def __init__(self):
        super().__init__(name="Claude Code")
        self.prompts: list[str] = []

    async def turn(self, prompt):
        self.prompts.append(prompt)
        yield ("tool", "Read")
        yield ("say", f"You said {prompt}.")


class FakeSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, frame):
        kind, message = voice.decode(frame)
        assert kind == "message"
        self.sent.append(message)


def test_relay_turns_go_to_the_agent_and_its_words_are_spoken():
    out = io.StringIO()
    agent = FakeAgent()
    client = voice.VoiceClient("ws://x", "t", voice.Printer(out, color=False), agent=agent)
    ws = FakeSocket()

    async def run():
        task = asyncio.create_task(client._relay(ws))
        client.handle(
            {
                "type": "server-message",
                "data": {"type": "manifest.turn", "id": "1", "text": "open my notes"},
            }
        )
        for _ in range(50):
            await asyncio.sleep(0.01)
            if len(ws.sent) >= 2:
                break
        task.cancel()

    asyncio.run(run())
    says = [m["data"]["d"]["text"] for m in ws.sent if m["data"]["t"] == "manifest.say"]
    assert says == ["Claude Code is listening.", "You said open my notes."]
    assert all(m["type"] == "client-message" for m in ws.sent)
    assert agent.prompts == ["open my notes"]
    assert "Claude Code: Read" in out.getvalue()
    client.handle({"type": "bot-output", "data": {"text": "Hi.", "aggregated_by": "sentence"}})
    assert "claude code  Hi." in out.getvalue()


def test_relay_mode_uses_its_own_url():
    assert voice.live_url("https://manifest.app", "relay").endswith("live?path=%2Fcli&mode=relay")
    assert "mode=" not in voice.live_url("https://manifest.app")


def test_claude_answers_are_spoken_sentence_by_sentence_as_they_stream():
    agent = agents.make_agent("claude")
    assert "--include-partial-messages" in agent.command()[0]

    def delta(t: str) -> str:
        return json.dumps(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": t},
                },
            }
        )

    agent.parse(json.dumps({"type": "stream_event", "event": {"type": "message_start"}}))
    assert agent.parse(delta("The sea is end")) == []
    assert agent.parse(delta("less, e.g. wide. Its waves ke")) == [
        ("say", "The sea is endless, e.g. wide.")
    ]
    assert agent.parse(delta("ep coming")) == []
    assert agent.parse(
        json.dumps({"type": "stream_event", "event": {"type": "content_block_stop"}})
    ) == [("say", "Its waves keep coming")]
    # The full message that follows is not spoken twice; tools still show.
    full = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "The sea..."},
                {"type": "tool_use", "name": "Read"},
            ]
        },
    }
    assert agent.parse(json.dumps(full)) == [("tool", "Read")]


def test_voice_uses_a_fast_model_unless_the_person_chose_one():
    def model_of(argv: list[str]) -> str | None:
        return argv[argv.index("--model") + 1] if "--model" in argv else None

    assert model_of(agents.make_agent("claude").command()[0]) == agents.CLAUDE_VOICE_MODEL
    assert model_of(agents.make_agent("claude", model="opus").command()[0]) == "opus"
    assert model_of(agents.make_agent("claude", model="default").command()[0]) is None
    own = agents.make_agent("claude", extra_args=["--model", "sonnet"]).command()[0]
    assert own.count("--model") == 1 and model_of(own) == "sonnet"

    codex = agents.make_agent("codex").command("hi")[0]
    assert 'model_reasoning_effort="low"' in codex
    assert (
        'model_reasoning_effort="low"'
        not in agents.make_agent("codex", model="default").command("hi")[0]
    )
    chosen = agents.make_agent("codex", model="gpt-5").command("hi")[0]
    assert chosen[chosen.index("-m") + 1] == "gpt-5"


def test_auto_picks_claude_code_then_codex(monkeypatch):
    found = {"codex"}
    monkeypatch.setattr(agents.shutil, "which", lambda b: f"/bin/{b}" if b in found else None)
    assert agents.make_agent("auto").name == "Codex"
    found.add("claude")
    assert agents.make_agent("auto").name == "Claude Code"


def test_interrupting_claude_sends_a_control_request():
    agent = agents.make_agent("claude")
    written: list[bytes] = []

    class Stdin:
        def write(self, data: bytes) -> None:
            written.append(data)

        async def drain(self) -> None:
            return None

    class Process:
        returncode = None
        stdin = Stdin()

    agent.process = Process()  # type: ignore[assignment]
    asyncio.run(agent.interrupt())
    body = json.loads(written[0])
    assert body["type"] == "control_request" and body["request"] == {"subtype": "interrupt"}


def test_the_voice_persona_sounds_like_a_person_and_stays_short():
    """Issue #131: warm, specific acknowledgements, honest, brief, never names feelings."""
    persona = agents.VOICE_PERSONA
    for rule in ("one breath", "React first", "never fawning", "Praise only what's earned"):
        assert rule in persona
    assert "never name or guess their feelings" in persona.lower()
    assert "don't end every reply with a question" in persona  # Hume EVI
    assert "say plainly you're an AI" in persona  # Pi, Hume
    assert "Don't lecture" in persona and "dates and money" in persona  # Hume EVI's default prompt
    assert len(persona) < 1700  # sent once per call (about 400 tokens), so it stays cheap
    assert agents.VOICE_STYLE.startswith(persona)


def test_markdown_is_never_read_aloud():
    assert agents.speakable("**Why it's promising**") == "Why it's promising"
    assert (
        agents.speakable("- Insurers are slow.\n2. Call five clinics.")
        == "Insurers are slow. Call five clinics."
    )
    assert (
        agents.speakable("See [the guide](https://x.example/a) or https://y.example")
        == "See the guide or the link"
    )
    assert agents.speakable("```\ncode\n```") == ""


def test_every_turn_reminds_the_agent_it_is_speaking():
    """A system prompt alone lost to the agent's defaults (200-400 words with markdown)."""
    codex = agents.make_agent("codex")
    assert codex.command("hi")[1].decode().endswith(agents.VOICE_TURN_HINT)
    codex.session_id = "t-1"
    assert codex.command("again")[1].decode() == f"again\n{agents.VOICE_TURN_HINT}"
