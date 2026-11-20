"""`manifest voice`: the hand-rolled protobuf matches Pipecat's, and messages print well."""

import io
import json

import pytest
from manifest_cli import main as cli
from manifest_cli import voice


def test_live_url_uses_websockets_and_keeps_paths():
    assert voice.live_url("https://manifeststartup.com") == (
        "wss://manifeststartup.com/api/voice-agent/live?path=%2Fcli"
    )
    assert voice.live_url("http://localhost:8000/").startswith(
        "ws://localhost:8000/api/voice-agent/live"
    )


def test_audio_and_messages_round_trip():
    kind, pcm = voice.decode(voice.encode_audio(b"\x01\x02" * 400))
    assert kind == "audio" and pcm == b"\x01\x02" * 400
    kind, msg = voice.decode(voice.encode_message({"type": "bot-ready"}))
    assert kind == "message" and msg == {"type": "bot-ready"}


def test_encoding_matches_pipecats_own_protobuf():
    frames_pb2 = pytest.importorskip("pipecat.frames.protobufs.frames_pb2")
    frame = frames_pb2.Frame.FromString(voice.encode_audio(b"\x00\x01" * 160))
    assert frame.audio.sample_rate == 16000 and frame.audio.num_channels == 1
    assert frame.audio.audio == b"\x00\x01" * 160
    theirs = frames_pb2.Frame(
        message=frames_pb2.MessageFrame(data=json.dumps({"a": 1}))
    ).SerializeToString()
    assert voice.decode(theirs) == ("message", {"a": 1})
    audio = frames_pb2.Frame(
        audio=frames_pb2.AudioRawFrame(
            id=7, name="x", audio=b"pcm", sample_rate=24000, num_channels=1
        )
    ).SerializeToString()
    assert voice.decode(audio) == ("audio", b"pcm")


def _client() -> tuple[voice.VoiceClient, io.StringIO]:
    out = io.StringIO()
    return voice.VoiceClient("ws://x", "t", voice.Printer(out, color=False)), out


def test_conversation_prints_like_a_transcript():
    client, out = _client()
    client.handle({"type": "user-transcription", "data": {"text": "list my ideas", "final": True}})
    client.handle(
        {"type": "bot-output", "data": {"text": "You have two.", "aggregated_by": "sentence"}}
    )
    client.handle(
        {"type": "bot-output", "data": {"text": "You have two.", "aggregated_by": "sentence"}}
    )
    client.handle(
        {
            "type": "server-message",
            "data": {
                "type": "manifest.tool",
                "phase": "finished",
                "label": "Delete idea",
                "ok": True,
                "summary": "Waiting for your yes",
            },
        }
    )
    client.handle({"type": "server-message", "data": {"type": "manifest.end"}})
    text = out.getvalue()
    assert "you  list my ideas" in text
    assert text.count("manifest  You have two.") == 1
    assert "✓ Delete idea — Waiting for your yes" in text
    assert client.ended.is_set()


def test_mic_is_muted_while_manifest_speaks_unless_barge_in():
    client, _ = _client()
    client.handle({"type": "bot-started-speaking"})
    assert client.bot_speaking and not client.barge_in
    client.handle({"type": "bot-stopped-speaking"})
    assert not client.bot_speaking


def test_voice_command_requires_login(monkeypatch, tmp_path):
    monkeypatch.setenv("MANIFEST_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.delenv("MANIFEST_API_TOKEN", raising=False)
    err = io.StringIO()
    code = cli.main(["voice", "--text"], out=io.StringIO(), err=err)
    assert code != 0 and "manifest login" in err.getvalue()
