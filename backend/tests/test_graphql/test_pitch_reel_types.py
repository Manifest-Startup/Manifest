"""Unit tests for pitch reel GraphQL type mappers."""

from datetime import datetime, timezone

from app.graphql.pitch_reel_types import map_pitch_reel, map_pitch_reel_comment


def test_map_pitch_reel_minimal_payload():
    created = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    reel = map_pitch_reel(
        {
            "reel_id": "r1",
            "slug": "s",
            "title": "T",
            "tags": ["x"],
            "video_url": "https://example.com/v.mp4",
            "workspace_path": "/ideas",
            "accent_from": "#000",
            "accent_to": "#fff",
            "created_at": created,
            "creator": {"user_id": "u1", "name": "N", "initials": "NI"},
            "stats": {},
            "viewer_state": {},
            "idea_id": "  i1  ",
        }
    )
    assert reel.reel_id == "r1"
    assert reel.idea_id == "i1"


def test_map_pitch_reel_comment():
    c = map_pitch_reel_comment(
        {
            "comment_id": "c1",
            "reel_id": "r1",
            "author_id": "u1",
            "author_name": "Bob",
            "body": "hi",
            "created_at": "2026-05-01T12:00:00+00:00",
            "is_mine": True,
        }
    )
    assert c.comment_id == "c1"
    assert c.is_mine is True
