"""Pitch reel video worker: Veo cost guard and posting to Open Media (no live calls)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import app.services.pitch_reels.video_worker as worker
import pytest
from app.services.integrations.open_media.client import OpenMediaNotLinked, OpenMediaUnavailable


@pytest.fixture
def env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPEN_MEDIA_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    svc = MagicMock()
    svc.get_reel.return_value = {
        "reel_id": "reel-1",
        "idea_id": "idea-1",
        "creator_user_id": "founder",
        "title": "Tidy",
        "thesis": "Cleaner books",
        "is_published": True,
        "om_post_id": None,
        "video_generated_at": None,
    }
    monkeypatch.setattr(worker, "create_database_client", MagicMock())
    monkeypatch.setattr(worker, "create_pitch_reel_service", MagicMock(return_value=svc))
    out = tmp_path / "reel-1.mp4"
    monkeypatch.setattr(worker, "_temp_output_path", lambda rid: out)
    monkeypatch.setattr(worker.identity, "handle_for_user", lambda uid: "founder")
    veo = MagicMock(side_effect=lambda t, d, path: path.write_bytes(b"x" * 64) or True)
    monkeypatch.setattr(worker, "generate_pitch_video_to_path", veo)
    uploads = []
    posts = []
    monkeypatch.setattr(
        worker.clips, "upload_video", lambda uid, data, ct: uploads.append((uid, len(data))) or {"path": "v"}
    )
    monkeypatch.setattr(
        worker.clips, "create_post", lambda uid, **kw: posts.append((uid, kw)) or {"id": "post-1"}
    )
    return {"svc": svc, "veo": veo, "uploads": uploads, "posts": posts, "out": out}


def _last_update(svc):
    return svc.update_reel_video_fields.call_args_list[-1]


def test_generates_uploads_and_posts_as_the_founder(env):
    worker.run_pitch_reel_video_job("reel-1", "Tidy", "Cleaner books")

    assert env["veo"].call_count == 1
    assert env["uploads"] == [("founder", 64)]
    uid, kwargs = env["posts"][0]
    assert uid == "founder"
    assert kwargs["video"] == {"path": "v"}
    assert kwargs["context"] == {
        "app": "manifest",
        "idea_id": "idea-1",
        "title": "Tidy",
        "url": "https://manifeststartup.com/pitch-reels?clip=reel-1",
    }
    assert _last_update(env["svc"]).kwargs == {"video_status": "ready", "om_post_id": "post-1"}
    assert not env["out"].exists()


def test_unlinked_founder_waits_without_calling_veo(env, monkeypatch):
    monkeypatch.setattr(worker.identity, "handle_for_user", lambda uid: None)
    worker.run_pitch_reel_video_job("reel-1", "Tidy", "Cleaner books")
    env["veo"].assert_not_called()
    assert _last_update(env["svc"]).kwargs == {"video_status": "needs_open_media"}


def test_recent_generation_is_not_repeated(env):
    env["svc"].get_reel.return_value["video_generated_at"] = (
        datetime.now(UTC) - timedelta(days=2)
    ).isoformat()
    worker.run_pitch_reel_video_job("reel-1", "Tidy", "Cleaner books")
    env["veo"].assert_not_called()
    assert _last_update(env["svc"]).kwargs["video_status"] == "failed"


def test_failed_upload_keeps_the_file_and_the_retry_skips_veo(env, monkeypatch):
    def down(uid, data, ct):
        raise OpenMediaUnavailable("down", status=503)

    monkeypatch.setattr(worker.clips, "upload_video", down)
    worker.run_pitch_reel_video_job("reel-1", "Tidy", "Cleaner books")
    assert _last_update(env["svc"]).kwargs["video_status"] == "failed"
    assert env["out"].exists()

    monkeypatch.setattr(worker.clips, "upload_video", lambda uid, data, ct: {"path": "v"})
    worker.run_pitch_reel_video_job("reel-1", "Tidy", "Cleaner books")
    assert env["veo"].call_count == 1  # second run re-used the MP4
    assert _last_update(env["svc"]).kwargs["om_post_id"] == "post-1"


def test_link_lost_during_upload_returns_to_needs_open_media(env, monkeypatch):
    def unlinked(uid, data, ct):
        raise OpenMediaNotLinked(reconnect=True)

    monkeypatch.setattr(worker.clips, "upload_video", unlinked)
    worker.run_pitch_reel_video_job("reel-1", "Tidy", "Cleaner books")
    assert _last_update(env["svc"]).kwargs == {"video_status": "needs_open_media"}
    assert env["out"].exists()


def test_without_google_key_no_veo_call(env, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY")
    worker.run_pitch_reel_video_job("reel-1", "Tidy", "Cleaner books")
    env["veo"].assert_not_called()
    assert _last_update(env["svc"]).kwargs["video_status"] == "failed"


def test_already_posted_or_unpublished_reels_are_skipped(env):
    env["svc"].get_reel.return_value["om_post_id"] = "post-0"
    worker.run_pitch_reel_video_job("reel-1", "Tidy", "Cleaner books")
    env["veo"].assert_not_called()
    env["svc"].update_reel_video_fields.assert_not_called()


def test_schedule_is_a_no_op_when_open_media_is_off(monkeypatch):
    monkeypatch.delenv("OPEN_MEDIA_ENABLED", raising=False)
    started = MagicMock()
    monkeypatch.setattr(worker, "Thread", started)
    worker.schedule_pitch_reel_video_generation("reel-1", "T", "D")
    started.assert_not_called()


def test_schedule_respects_disabled_video_mode(monkeypatch):
    monkeypatch.setenv("OPEN_MEDIA_ENABLED", "1")
    monkeypatch.setenv("PITCH_REEL_VIDEO_MODE", "disabled")
    started = MagicMock()
    monkeypatch.setattr(worker, "Thread", started)
    worker.schedule_pitch_reel_video_generation("reel-1", "T", "D")
    started.assert_not_called()


def test_linking_resumes_waiting_reels(monkeypatch):
    monkeypatch.setenv("OPEN_MEDIA_ENABLED", "1")
    svc = MagicMock()
    svc.reels_waiting_for_open_media.return_value = [
        {"reel_id": "r1", "title": "T", "description": "D", "is_published": True}
    ]
    monkeypatch.setattr(worker, "create_database_client", MagicMock())
    monkeypatch.setattr(worker, "create_pitch_reel_service", MagicMock(return_value=svc))
    scheduled = []
    monkeypatch.setattr(
        worker, "schedule_pitch_reel_video_generation", lambda *a: scheduled.append(a)
    )
    assert worker.resume_reels_waiting_for_open_media("founder") == 1
    assert scheduled == [("r1", "T", "D")]
    svc.update_reel_video_fields.assert_called_once_with("r1", video_status="pending")
