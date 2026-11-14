"""Tests for background pitch reel video worker wiring (no live Gemini calls)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import app.services.pitch_reels.video_worker as worker
from app.services.pitch_reels.media import PublishedPitchReelMedia


def test_run_pitch_reel_video_job_without_google_key_sets_ready_placeholder(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    mock_svc = MagicMock()
    mock_create_svc = MagicMock(return_value=mock_svc)

    with patch.object(worker, "create_database_client", return_value=MagicMock()):
        with patch.object(worker, "create_pitch_reel_service", mock_create_svc):
            from app.services.pitch_reels.service import USER_REEL_PLACEHOLDER_VIDEO

            worker.run_pitch_reel_video_job("reel-uuid", "Title", "Desc")

    mock_svc.update_reel_video_fields.assert_called_once()
    kwargs = mock_svc.update_reel_video_fields.call_args[1]
    assert kwargs["video_status"] == "ready"
    assert kwargs["video_url"] == USER_REEL_PLACEHOLDER_VIDEO


def test_run_pitch_reel_video_job_prefers_storage_url_when_available(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    output_path = tmp_path / "reel.mp4"
    output_path.write_bytes(b"fake-video")

    mock_svc = MagicMock()

    with patch.object(worker, "create_database_client", return_value=MagicMock()):
        with patch.object(worker, "create_pitch_reel_service", return_value=mock_svc):
            with patch.object(worker, "_temp_output_path", return_value=output_path):
                with patch.object(worker, "generate_pitch_video_to_path", return_value=True):
                    with patch.object(
                        worker,
                        "publish_reel_video_bytes",
                        return_value=PublishedPitchReelMedia(
                            playback_url="https://cdn.example.com/pitch-reels/reel-uuid/master.m3u8",
                            storage_path="hls/reel-uuid/master.m3u8",
                            hls_manifest_url="https://cdn.example.com/pitch-reels/reel-uuid/master.m3u8",
                            hls_manifest_path="hls/reel-uuid/master.m3u8",
                        ),
                    ):
                        worker.run_pitch_reel_video_job("reel-uuid", "Title", "Desc")

    mock_svc.store_reel_video_data.assert_not_called()
    mock_svc.clear_reel_video_data.assert_called_once_with("reel-uuid")
    final_update = mock_svc.update_reel_video_fields.call_args_list[-1].kwargs
    assert final_update["video_status"] == "ready"
    assert final_update["video_url"] == "https://cdn.example.com/pitch-reels/reel-uuid/master.m3u8"


def test_run_pitch_reel_video_job_falls_back_to_db_storage_when_upload_unavailable(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    output_path = tmp_path / "reel.mp4"
    output_path.write_bytes(b"fake-video")

    mock_svc = MagicMock()

    with patch.object(worker, "create_database_client", return_value=MagicMock()):
        with patch.object(worker, "create_pitch_reel_service", return_value=mock_svc):
            with patch.object(worker, "_temp_output_path", return_value=output_path):
                with patch.object(worker, "generate_pitch_video_to_path", return_value=True):
                    with patch.object(worker, "publish_reel_video_bytes", return_value=None):
                        worker.run_pitch_reel_video_job("reel-uuid", "Title", "Desc")

    mock_svc.store_reel_video_data.assert_called_once_with("reel-uuid", b"fake-video")
    final_update = mock_svc.update_reel_video_fields.call_args_list[-1].kwargs
    assert final_update["video_status"] == "ready"
    assert final_update["video_url"] == "/api/pitch-reels/reel-uuid/video"
