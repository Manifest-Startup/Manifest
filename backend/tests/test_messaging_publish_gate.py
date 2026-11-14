"""Tests for published-idea gate on founder messaging."""

from unittest.mock import MagicMock

import pytest

from app.services.messaging_service import MessagingService


class _ExecResult:
    def __init__(self, data):
        self.data = data


@pytest.mark.asyncio
async def test_require_messaging_allowed_skips_when_idea_missing():
    db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = _ExecResult(None)
    db.table.return_value = chain

    svc = MessagingService(db)
    await svc.require_messaging_allowed_for_idea("missing", "viewer-1")
    db.table.assert_called_with("ideas")


@pytest.mark.asyncio
async def test_require_messaging_allowed_non_owner_unpublished_raises():
    db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = _ExecResult({"user_id": "owner-1", "is_published": False})
    db.table.return_value = chain

    svc = MessagingService(db)
    with pytest.raises(ValueError, match="published"):
        await svc.require_messaging_allowed_for_idea("idea-1", "viewer-1")


@pytest.mark.asyncio
async def test_require_messaging_allowed_non_owner_published_ok():
    db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = _ExecResult({"user_id": "owner-1", "is_published": True})
    db.table.return_value = chain

    svc = MessagingService(db)
    await svc.require_messaging_allowed_for_idea("idea-1", "viewer-1")


@pytest.mark.asyncio
async def test_require_messaging_allowed_owner_unpublished_ok():
    db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = _ExecResult({"user_id": "owner-1", "is_published": False})
    db.table.return_value = chain

    svc = MessagingService(db)
    await svc.require_messaging_allowed_for_idea("idea-1", "owner-1")
