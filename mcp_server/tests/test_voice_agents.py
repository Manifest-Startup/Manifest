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
    assert "out loud" in argv[argv.index("--append-system-prompt") + 1]

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
    assert stdin.endswith(b"hi") and b"out loud" in stdin
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
    delta = lambda t: json.dumps(
        {
            "type": "stream_event",
            "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": t}},
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
