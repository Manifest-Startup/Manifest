"""Unit tests for Gemini / Veo pitch video helper (no live API calls)."""

from pathlib import Path

from app.services import gemini_video_service as gvs


def test_build_pitch_prompt_includes_title_and_description():
    p = gvs._build_pitch_prompt("Acme AI", "We automate compliance for SMBs.")
    assert "Acme AI" in p
    assert "compliance" in p.lower()


def test_build_pitch_prompt_title_only():
    p = gvs._build_pitch_prompt("Solo Title", "")
    assert "Solo Title" in p


def test_generate_pitch_video_returns_false_without_api_key(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    out = tmp_path / "v.mp4"
    assert gvs.generate_pitch_video_to_path("T", "D", out, timeout_seconds=1) is False
