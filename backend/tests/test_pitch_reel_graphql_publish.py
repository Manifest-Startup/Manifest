"""GraphQL publish / pitch reel resolver behavior (mocked DB and services)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_pitch_reels_feed_calls_list_feed_with_viewer_id_kwarg():
    """Regression: list_feed must receive viewer_id=..., not user_id=."""
    mock_service = MagicMock()
    mock_service.list_feed = AsyncMock(return_value=[])

    info = MagicMock()
    info.context = {"db": MagicMock(), "request": MagicMock()}

    with patch("app.graphql.schema.get_current_user_id", return_value="viewer-uuid-1"):
        with patch(
            "app.services.pitch_reel_service.create_pitch_reel_service",
            return_value=mock_service,
        ):
            from app.graphql.schema import Query

            q = Query()
            await q.pitch_reels_feed(info, limit=12)

    mock_service.list_feed.assert_awaited_once()
    call_kw = mock_service.list_feed.await_args.kwargs
    assert call_kw.get("viewer_id") == "viewer-uuid-1"
    assert call_kw.get("limit") == 12
    assert "user_id" not in call_kw


def _ideas_table_mocks(*, idea_row: dict, update_rows: list):
    """Two successive db.table('ideas') chains: select+single, then update."""
    check_chain = MagicMock()
    check_chain.select.return_value = check_chain
    check_chain.eq.return_value = check_chain
    check_chain.single.return_value = check_chain
    check_chain.execute.return_value = MagicMock(data=idea_row)

    update_chain = MagicMock()
    update_chain.update.return_value = update_chain
    update_chain.eq.return_value = update_chain
    update_chain.execute.return_value = MagicMock(data=update_rows)

    it = iter([check_chain, update_chain])

    def table_side(name: str):
        if name == "ideas":
            return next(it)
        return MagicMock()

    db = MagicMock()
    db.table.side_effect = table_side
    return db


@pytest.mark.asyncio
async def test_toggle_publish_idea_publish_path_upserts_reel_and_schedules_video():
    idea_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    user_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    idea_row = {
        "idea_id": idea_id,
        "is_published": False,
        "title": "Rocket Fuel",
        "description": "Sustainable propellant",
    }
    db = _ideas_table_mocks(idea_row=idea_row, update_rows=[{"idea_id": idea_id}])
    info = MagicMock()
    info.context = {"db": db, "request": MagicMock()}

    mock_reel_svc = MagicMock()
    mock_reel_svc.upsert_reel_for_published_idea.return_value = ("reel-uuid-9", True)

    with patch("app.graphql.schema.get_current_user_id", return_value=user_id):
        with patch("app.services.guest_workspace_service.fetch_user_is_guest", return_value=False):
            with patch(
                "app.services.pitch_reel_service.create_pitch_reel_service",
                return_value=mock_reel_svc,
            ):
                with patch(
                    "app.services.pitch_reel_video_worker.schedule_pitch_reel_video_generation",
                ) as mock_schedule:
                    with patch.dict("os.environ", {"PITCH_REEL_VIDEO_MODE": "thread"}, clear=False):
                        from app.graphql.schema import Mutation

                        m = Mutation()
                        result = await m.toggle_publish_idea(info, idea_id=idea_id)

    assert result.idea_id == idea_id
    assert result.is_published is True
    mock_reel_svc.upsert_reel_for_published_idea.assert_called_once_with(
        idea_id,
        user_id,
        "Rocket Fuel",
        "Sustainable propellant",
    )
    mock_schedule.assert_called_once_with(
        "reel-uuid-9",
        "Rocket Fuel",
        "Sustainable propellant",
    )


@pytest.mark.asyncio
async def test_toggle_publish_idea_respects_pitch_reel_video_mode_disabled(monkeypatch):
    monkeypatch.setenv("PITCH_REEL_VIDEO_MODE", "disabled")
    idea_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    user_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    idea_row = {
        "idea_id": idea_id,
        "is_published": False,
        "title": "T",
        "description": "D",
    }
    db = _ideas_table_mocks(idea_row=idea_row, update_rows=[{"idea_id": idea_id}])
    info = MagicMock()
    info.context = {"db": db, "request": MagicMock()}

    mock_reel_svc = MagicMock()
    mock_reel_svc.upsert_reel_for_published_idea.return_value = ("reel-x", True)

    with patch("app.graphql.schema.get_current_user_id", return_value=user_id):
        with patch("app.services.guest_workspace_service.fetch_user_is_guest", return_value=False):
            with patch(
                "app.services.pitch_reel_service.create_pitch_reel_service",
                return_value=mock_reel_svc,
            ):
                with patch(
                    "app.services.pitch_reel_video_worker.schedule_pitch_reel_video_generation",
                ) as mock_schedule:
                    from app.graphql.schema import Mutation

                    m = Mutation()
                    await m.toggle_publish_idea(info, idea_id=idea_id)

    mock_schedule.assert_not_called()


@pytest.mark.asyncio
async def test_toggle_publish_idea_unpublish_calls_unpublish_reel():
    idea_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    user_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    idea_row = {
        "idea_id": idea_id,
        "is_published": True,
        "title": "Was live",
        "description": "X",
    }
    db = _ideas_table_mocks(idea_row=idea_row, update_rows=[{"idea_id": idea_id}])
    info = MagicMock()
    info.context = {"db": db, "request": MagicMock()}

    mock_reel_svc = MagicMock()

    with patch("app.graphql.schema.get_current_user_id", return_value=user_id):
        with patch("app.services.guest_workspace_service.fetch_user_is_guest", return_value=False):
            with patch(
                "app.services.pitch_reel_service.create_pitch_reel_service",
                return_value=mock_reel_svc,
            ):
                with patch(
                    "app.services.pitch_reel_video_worker.schedule_pitch_reel_video_generation",
                ) as mock_schedule:
                    from app.graphql.schema import Mutation

                    m = Mutation()
                    result = await m.toggle_publish_idea(info, idea_id=idea_id)

    assert result.is_published is False
    mock_reel_svc.unpublish_reel_for_idea.assert_called_once_with(idea_id)
    mock_reel_svc.upsert_reel_for_published_idea.assert_not_called()
    mock_schedule.assert_not_called()


def test_map_pitch_reel_includes_idea_id_when_present():
    from datetime import datetime, timezone

    from app.graphql.schema import map_pitch_reel

    idea_uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    payload = {
        "reel_id": "r1",
        "slug": "s",
        "title": "T",
        "tags": [],
        "video_url": "https://x",
        "workspace_path": "/ideas",
        "accent_from": "#000",
        "accent_to": "#fff",
        "created_at": datetime.now(timezone.utc),
        "idea_id": idea_uuid,
        "creator": {"user_id": "u1", "name": "N", "initials": "N"},
        "stats": {},
        "viewer_state": {},
    }
    mapped = map_pitch_reel(payload)
    assert mapped.idea_id == idea_uuid


def test_map_pitch_reel_idea_id_none_when_missing_or_blank():
    from datetime import datetime, timezone

    from app.graphql.schema import map_pitch_reel

    base = {
        "reel_id": "r1",
        "slug": "s",
        "title": "T",
        "tags": [],
        "video_url": "https://x",
        "workspace_path": "/ideas",
        "accent_from": "#000",
        "accent_to": "#fff",
        "created_at": datetime.now(timezone.utc),
        "creator": {"user_id": "u1", "name": "N", "initials": "N"},
        "stats": {},
        "viewer_state": {},
    }
    assert map_pitch_reel({**base}).idea_id is None
    assert map_pitch_reel({**base, "idea_id": ""}).idea_id is None
    assert map_pitch_reel({**base, "idea_id": "   "}).idea_id is None
