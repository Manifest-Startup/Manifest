"""Tests for skills feature: available_skills query, update_account skills, update_idea required_skills."""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graphql.schema import AVAILABLE_SKILLS, Mutation, Query

_CREATED_AT = "2026-01-01T00:00:00"
_CREATED_AT_DT = datetime(2026, 1, 1)


def _make_user_row(user_id: str, extra: dict | None = None) -> dict:
    base = {
        "user_id": user_id,
        "email": "test@example.com",
        "username": None,
        "first_name": None,
        "last_name": None,
        "country": None,
        "bio": None,
        "address": None,
        "state": None,
        "gravatar_hash": None,
        "profile_picture_url": None,
        "skills": [],
        "created_at": _CREATED_AT_DT,
    }
    if extra:
        base.update(extra)
    return base


def _make_idea_row(idea_id: str, user_id: str, extra: dict | None = None) -> dict:
    base = {
        "idea_id": idea_id,
        "user_id": user_id,
        "title": "Test Idea",
        "description": None,
        "pitch_deck": None,
        "product_requirements_document": None,
        "provisional_patent": None,
        "business_model_canvas": None,
        "similar_ideas": None,
        "required_skills": [],
        "created_at": _CREATED_AT_DT,
        "is_published": False,
    }
    if extra:
        base.update(extra)
    return base


# ---------------------------------------------------------------------------
# available_skills query
# ---------------------------------------------------------------------------


def test_available_skills_returns_list():
    query = Query()
    result = query.available_skills()
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(s, str) for s in result)


def test_available_skills_matches_constant():
    query = Query()
    assert query.available_skills() == AVAILABLE_SKILLS


def test_available_skills_contains_expected_entries():
    query = Query()
    skills = query.available_skills()
    assert "Full Stack Development" in skills
    assert "Machine Learning / AI" in skills
    assert "Product Management" in skills


# ---------------------------------------------------------------------------
# update_account saves skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_account_saves_skills():
    user_id = str(uuid.uuid4())
    skills = ["Full Stack Development", "Product Management"]

    from app.graphql.schema import AccountUpdateInput

    input_obj = AccountUpdateInput(skills=skills)

    db = MagicMock()
    update_resp = MagicMock()
    update_resp.data = [_make_user_row(user_id, {"skills": skills})]
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = update_resp

    info = MagicMock()
    info.context = {"request": MagicMock(), "response": MagicMock(), "db": db}

    with patch("app.graphql.schema.get_current_user_id", return_value=user_id):
        mutation = Mutation()
        result = await mutation.update_account(info, input_obj)

    db.table.assert_called_with("users")
    update_payload = db.table.return_value.update.call_args[0][0]
    assert update_payload.get("skills") == skills


@pytest.mark.asyncio
async def test_update_account_skips_skills_when_none():
    user_id = str(uuid.uuid4())

    from app.graphql.schema import AccountUpdateInput

    input_obj = AccountUpdateInput(first_name="Ada")

    db = MagicMock()
    update_resp = MagicMock()
    update_resp.data = [_make_user_row(user_id, {"first_name": "Ada"})]
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = update_resp

    info = MagicMock()
    info.context = {"request": MagicMock(), "response": MagicMock(), "db": db}

    with patch("app.graphql.schema.get_current_user_id", return_value=user_id):
        mutation = Mutation()
        await mutation.update_account(info, input_obj)

    update_payload = db.table.return_value.update.call_args[0][0]
    assert "skills" not in update_payload


# ---------------------------------------------------------------------------
# update_idea saves required_skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_idea_saves_required_skills():
    user_id = str(uuid.uuid4())
    idea_id = str(uuid.uuid4())
    skills = ["Backend Development", "DevOps / Cloud"]

    db = MagicMock()
    update_resp = MagicMock()
    update_resp.data = [_make_idea_row(idea_id, user_id, {"required_skills": skills})]
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = update_resp

    info = MagicMock()
    info.context = {"request": MagicMock(), "response": MagicMock(), "db": db}

    mock_collab = MagicMock()
    mock_collab.check_access = AsyncMock(return_value=True)

    import app.services.ideas.collaboration as _collab_mod
    import app.utils.idea_utils as _idea_utils_mod
    _orig_collab = _collab_mod.create_collaboration_service
    _orig_bg = _idea_utils_mod.generate_background_tasks
    _collab_mod.create_collaboration_service = lambda _db: mock_collab
    _idea_utils_mod.generate_background_tasks = MagicMock()
    try:
        with patch("app.graphql.schema.get_current_user_id", return_value=user_id):
            mutation = Mutation()
            result = await mutation.update_idea(info, idea_id, required_skills=skills)
    finally:
        _collab_mod.create_collaboration_service = _orig_collab
        _idea_utils_mod.generate_background_tasks = _orig_bg

    update_payload = db.table.return_value.update.call_args[0][0]
    assert update_payload.get("required_skills") == skills


@pytest.mark.asyncio
async def test_update_idea_skips_required_skills_when_none():
    user_id = str(uuid.uuid4())
    idea_id = str(uuid.uuid4())

    db = MagicMock()
    update_resp = MagicMock()
    update_resp.data = [_make_idea_row(idea_id, user_id, {"title": "Updated Title"})]
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = update_resp

    info = MagicMock()
    info.context = {"request": MagicMock(), "response": MagicMock(), "db": db}

    mock_collab = MagicMock()
    mock_collab.check_access = AsyncMock(return_value=True)

    import app.services.ideas.collaboration as _collab_mod
    import app.utils.idea_utils as _idea_utils_mod
    _orig_collab = _collab_mod.create_collaboration_service
    _orig_bg = _idea_utils_mod.generate_background_tasks
    _collab_mod.create_collaboration_service = lambda _db: mock_collab
    _idea_utils_mod.generate_background_tasks = MagicMock()
    try:
        with patch("app.graphql.schema.get_current_user_id", return_value=user_id):
            mutation = Mutation()
            await mutation.update_idea(info, idea_id, title="Updated Title")
    finally:
        _collab_mod.create_collaboration_service = _orig_collab
        _idea_utils_mod.generate_background_tasks = _orig_bg

    update_payload = db.table.return_value.update.call_args[0][0]
    assert "required_skills" not in update_payload
