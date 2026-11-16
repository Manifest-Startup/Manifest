"""Pitch Shorts feed: Manifest reels joined with Open Media clips."""

import pytest
from app.db.database import InMemoryDatabaseClient
from app.services.integrations.open_media.client import OpenMediaUnavailable
from app.services.pitch_reels import service as reel_service
from app.services.pitch_reels.service import DEMO_REEL_IDS, PitchReelService


def _reel(reel_id, *, post=None, published=True, created="2026-11-01", **extra):
    return {
        "reel_id": reel_id,
        "idea_id": f"idea-{reel_id}",
        "creator_user_id": "founder",
        "title": f"Title {reel_id}",
        "description": "<p>Long note content.</p>" * 200,
        "om_post_id": post,
        "video_status": "ready" if post else "pending",
        "is_published": published,
        "created_at": created,
        **extra,
    }


def _clip(post_id, **extra):
    return {
        "id": post_id,
        "video_url": f"https://cdn.openmedia.site/{post_id}.mp4",
        "poster_url": None,
        "author": {"id": "om-founder", "handle": "founder", "display_name": "F", "avatar_url": None},
        "like_count": 3,
        "comment_count": 2,
        "reshare_count": 1,
        "viewer_liked": True,
        "viewer_reshared": False,
        **extra,
    }


@pytest.fixture
def db():
    store = InMemoryDatabaseClient()
    store.table("users").insert({"user_id": "founder", "username": "founder", "first_name": "Ada"}).execute()
    return store


@pytest.mark.asyncio
async def test_feed_joins_clips_in_open_media_order_then_waiting_reels(db, monkeypatch):
    for row in (
        _reel("a", post="p-a", created="2026-11-03"),
        _reel("b", post="p-b", created="2026-11-02"),
        _reel("waiting", created="2026-11-04"),
        _reel("draft", post="p-draft", published=False),
        _reel(DEMO_REEL_IDS[0], post="p-demo"),
    ):
        db.table("pitch_reels").insert(row).execute()
    seen = {}

    def fake_feed(viewer):
        seen["viewer"] = viewer
        return [_clip("p-b"), _clip("p-unknown"), _clip("p-a", viewer_liked=False), _clip("p-demo")]

    monkeypatch.setattr(reel_service.clips, "feed", fake_feed)
    feed = await PitchReelService(db).list_feed("viewer", limit=10)

    assert seen["viewer"] == "viewer"
    assert [row["reel_id"] for row in feed] == ["b", "a", "waiting"]
    first = feed[0]
    assert first["video_url"] == "https://cdn.openmedia.site/p-b.mp4"
    assert first["stats"] == {"like_count": 3, "comment_count": 2, "share_count": 1}
    assert first["viewer_state"] == {"liked": True, "reshared": False}
    assert first["creator"]["handle"] == "founder"
    assert feed[1]["viewer_state"]["liked"] is False
    assert len(first["description"]) <= 641 and "<p>" not in first["description"]
    assert feed[2]["video_url"] == "" and feed[2]["video_status"] == "pending"


@pytest.mark.asyncio
async def test_feed_survives_an_open_media_outage(db, monkeypatch):
    db.table("pitch_reels").insert(_reel("a", post="p-a")).execute()

    def down(viewer):
        raise OpenMediaUnavailable("down", status=503)

    monkeypatch.setattr(reel_service.clips, "feed", down)
    feed = await PitchReelService(db).list_feed("viewer")
    assert [row["reel_id"] for row in feed] == []  # clip-backed reels need Open Media


@pytest.mark.asyncio
async def test_feed_respects_limit(db, monkeypatch):
    for idx in range(5):
        db.table("pitch_reels").insert(_reel(f"r{idx}", post=f"p{idx}")).execute()
    monkeypatch.setattr(reel_service.clips, "feed", lambda v: [_clip(f"p{i}") for i in range(5)])
    feed = await PitchReelService(db).list_feed("viewer", limit=2)
    assert [row["reel_id"] for row in feed] == ["r0", "r1"]


@pytest.mark.asyncio
async def test_empty_feed_does_not_call_open_media(db, monkeypatch):
    def boom(viewer):
        raise AssertionError("no reels, no Open Media call")

    monkeypatch.setattr(reel_service.clips, "feed", boom)
    assert await PitchReelService(db).list_feed("viewer") == []


@pytest.mark.asyncio
async def test_like_requires_a_posted_clip(db, monkeypatch):
    db.table("pitch_reels").insert(_reel("waiting")).execute()
    db.table("pitch_reels").insert(_reel("a", post="p-a")).execute()
    calls = []
    monkeypatch.setattr(
        reel_service.clips,
        "set_like",
        lambda uid, pid, liked: calls.append((uid, pid, liked)) or {"like_count": 4},
    )
    svc = PitchReelService(db)
    with pytest.raises(ValueError, match="not ready"):
        await svc.set_like("waiting", "viewer", True)
    result = await svc.set_like("a", "viewer", True)
    assert calls == [("viewer", "p-a", True)]
    assert result == {"reel_id": "a", "liked": True, "like_count": 4}
