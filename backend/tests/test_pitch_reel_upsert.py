"""Unit tests for pitch reel rows created when ideas are published."""

from unittest.mock import MagicMock

from app.services.pitch_reel_service import PitchReelService, USER_REEL_PLACEHOLDER_VIDEO


def test_unpublish_reel_for_idea_updates_row():
    db = MagicMock()
    chain = MagicMock()
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.execute.return_value = MagicMock()
    db.table.return_value = chain

    svc = PitchReelService(db)
    svc.unpublish_reel_for_idea("550e8400-e29b-41d4-a716-446655440000")

    db.table.assert_called_with("pitch_reels")
    chain.update.assert_called_once()
    call_kw = chain.update.call_args[0][0]
    assert call_kw.get("is_published") is False


def test_upsert_reel_for_published_idea_inserts_when_none_exist():
    select_chain = MagicMock()
    select_chain.select.return_value = select_chain
    select_chain.eq.return_value = select_chain
    select_chain.limit.return_value = select_chain
    select_chain.execute.return_value = MagicMock(data=[])

    insert_chain = MagicMock()
    insert_tail = MagicMock()
    insert_chain.insert.return_value = insert_tail
    insert_tail.execute.return_value = MagicMock()

    calls = {"n": 0}

    def table_side_effect(name):
        assert name == "pitch_reels"
        calls["n"] += 1
        return select_chain if calls["n"] == 1 else insert_chain

    db = MagicMock()
    db.table.side_effect = table_side_effect

    svc = PitchReelService(db)
    rid, needs_video = svc.upsert_reel_for_published_idea(
        "550e8400-e29b-41d4-a716-446655440000",
        "owner-uuid",
        "My Startup",
        "We build tools for founders.",
    )

    assert len(rid) == 36
    assert needs_video is True
    insert_chain.insert.assert_called_once()
    payload = insert_chain.insert.call_args[0][0]
    assert payload["video_url"] == USER_REEL_PLACEHOLDER_VIDEO
    assert payload["video_status"] == "pending"
    assert payload["idea_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert payload["workspace_path"] == "/ideas/550e8400-e29b-41d4-a716-446655440000"


def test_upsert_reel_for_published_idea_updates_when_exists():
    db = MagicMock()
    existing_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    select_chain = MagicMock()
    select_chain.select.return_value = select_chain
    select_chain.eq.return_value = select_chain
    select_chain.limit.return_value = select_chain
    select_chain.execute.return_value = MagicMock(data=[{"reel_id": existing_id, "slug": "idea-550e8400e29b41d4"}])

    update_chain = MagicMock()
    update_chain.update.return_value = update_chain
    update_chain.eq.return_value = update_chain
    update_chain.execute.return_value = MagicMock()

    calls = {"n": 0}

    def table_side_effect(name):
        assert name == "pitch_reels"
        calls["n"] += 1
        if calls["n"] == 1:
            return select_chain
        return update_chain

    db.table.side_effect = table_side_effect

    svc = PitchReelService(db)
    rid, needs_video = svc.upsert_reel_for_published_idea(
        "550e8400-e29b-41d4-a716-446655440000",
        "owner-uuid",
        "Updated Title",
        "New description text.",
    )

    assert rid == existing_id
    assert needs_video is True
    update_chain.update.assert_called_once()


def test_upsert_reel_for_published_idea_strips_html_from_description_and_title():
    select_chain = MagicMock()
    select_chain.select.return_value = select_chain
    select_chain.eq.return_value = select_chain
    select_chain.limit.return_value = select_chain
    select_chain.execute.return_value = MagicMock(data=[])

    insert_chain = MagicMock()
    insert_tail = MagicMock()
    insert_chain.insert.return_value = insert_tail
    insert_tail.execute.return_value = MagicMock()

    calls = {"n": 0}

    def table_side_effect(name):
        assert name == "pitch_reels"
        calls["n"] += 1
        return select_chain if calls["n"] == 1 else insert_chain

    db = MagicMock()
    db.table.side_effect = table_side_effect

    html_desc = (
        "<p>Property management, software.</p> "
        "<h2>Voice Strategy Session</h2> "
        "<p><strong>Working title:</strong> Student Housing</p>"
    )
    html_title = "<p>My <strong>Title</strong></p>"

    svc = PitchReelService(db)
    svc.upsert_reel_for_published_idea(
        "550e8400-e29b-41d4-a716-446655440000",
        "owner-uuid",
        html_title,
        html_desc,
    )

    payload = insert_chain.insert.call_args[0][0]
    assert "<p>" not in payload["description"]
    assert "<h2>" not in payload["subtitle"]
    assert payload["title"] == "My Title"
    assert "Property management, software." in (payload["description"] or "")
    assert "Student Housing" in (payload["description"] or "")
