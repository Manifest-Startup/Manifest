"""Voice capabilities catalog entries stay aligned with the web client."""

from app.services.voice_command_catalog import VOICE_COMMAND_CAPABILITIES, VOICE_COMMAND_CAPABILITY_SUMMARY


def test_voice_capabilities_include_generation_and_integrations():
    ids = {entry["id"] for entry in VOICE_COMMAND_CAPABILITIES}
    assert "ideas-generate" in ids
    assert "integrations-github" in ids
    assert "github" in VOICE_COMMAND_CAPABILITY_SUMMARY.lower()
