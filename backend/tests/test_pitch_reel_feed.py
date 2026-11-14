"""Feed regressions: real content, bounded queries, and nonblocking database I/O."""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest
from app.db.database import DatabaseClient, InMemoryDatabaseClient, QueryResponse
from app.services.pitch_reel_service import DEMO_REEL_IDS, PitchReelService


@pytest.mark.asyncio
async def test_samples_are_excluded_before_limit_without_hiding_real_names(monkeypatch):
    db = InMemoryDatabaseClient()
    for rid in DEMO_REEL_IDS:
        db.table("pitch_reels").insert(
            {
                "reel_id": rid,
                "is_published": True,
                "created_at": "2026-09-20",
            }
        ).execute()
    db.table("pitch_reels").insert(
        {
            "reel_id": "real-reel",
            "title": "AquaChain",
            "creator_user_id": "founder",
            "is_published": True,
            "created_at": "2026-09-01",
            "video_url": "/videos/tutorial.mov",
        }
    ).execute()
    db.table("pitch_reels").insert(
        {
            "reel_id": "draft",
            "is_published": False,
            "created_at": "2026-09-21",
        }
    ).execute()
    svc = PitchReelService(db)
    monkeypatch.setattr(svc, "_fetch_reel_ids_with_video_data", lambda _: set())
    feed = await svc.list_feed("viewer", limit=1)
    assert [row["reel_id"] for row in feed] == ["real-reel"]
    assert feed[0]["title"] == "AquaChain"
    assert feed[0]["video_url"] == ""


@pytest.mark.parametrize("placeholder", ["/videos/tutorial.mov", "/videos/founders-video.mov"])
def test_sample_video_is_never_used_as_a_real_pitch(placeholder):
    assert (
        PitchReelService._effective_video_url(
            reel_id="real", stored_video_url=placeholder, has_video_data=False
        )
        == ""
    )
    assert (
        PitchReelService._effective_video_url(
            reel_id="real", stored_video_url=placeholder, has_video_data=True
        )
        == "/api/pitch-reels/real/video"
    )


@pytest.mark.asyncio
async def test_postgres_feed_uses_one_query_and_preserves_viewer_state():
    db = DatabaseClient()
    db.execute_raw = MagicMock(
        return_value=QueryResponse(
            [
                {
                    "reel_id": "real",
                    "creator_user_id": "founder",
                    "title": "Real pitch",
                    "video_url": "",
                    "description": "<p>Long note content.</p>" * 1000,
                    "has_video_data": True,
                    "likes": 2,
                    "saves": 3,
                    "shares": 4,
                    "comments": 5,
                    "liked": True,
                    "saved": False,
                    "followers": 6,
                    "following": True,
                    "creator_record": {"username": "founder", "first_name": "Real"},
                }
            ]
        )
    )
    svc = PitchReelService(db)
    svc._fetch_reel_ids_with_video_data = MagicMock(side_effect=AssertionError("Extra connection"))
    feed = await svc.list_feed("viewer", 12)
    db.execute_raw.assert_called_once()
    sql, params = db.execute_raw.call_args.args
    assert params == (*DEMO_REEL_IDS, 12, "viewer", "viewer", "viewer")
    assert "r.video_data IS NOT NULL" in sql
    assert "SELECT r.*" not in sql
    assert len(feed[0]["description"]) <= 641
    assert feed[0]["description"].endswith("…")
    assert "<p>" not in feed[0]["description"]
    assert feed[0]["viewer_state"] == {"liked": True, "saved": False}
    assert feed[0]["stats"] == {
        "like_count": 2,
        "save_count": 3,
        "share_count": 4,
        "comment_count": 5,
    }
    assert feed[0]["creator"]["is_following"] is True
    assert feed[0]["creator"]["follower_count"] == 6
    assert feed[0]["video_url"] == "/api/pitch-reels/real/video"


@pytest.mark.asyncio
async def test_database_wait_does_not_block_other_requests():
    db = DatabaseClient()
    entered = threading.Event()
    release = threading.Event()

    def blocking_query(*_):
        entered.set()
        assert release.wait(timeout=2)
        return QueryResponse([])

    db.execute_raw = blocking_query
    task = asyncio.create_task(PitchReelService(db).list_feed("viewer"))
    try:
        # The event loop can still schedule work while PostgreSQL is waiting.
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.005)
        assert entered.is_set()
        assert not task.done()
    finally:
        release.set()
    assert await task == []
