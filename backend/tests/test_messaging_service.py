"""Tests for MessagingService response normalization and guard rails."""

from unittest.mock import MagicMock

import pytest

from app.services.social.messaging import MessagingService


class MockQueryResponse:
    def __init__(self, data):
        self.data = data


class MockQueryBuilder:
    def __init__(self, data=None):
        self._data = data
        self._single_mode = False

    def select(self, *args):
        return self

    def eq(self, *args):
        return self

    def is_(self, *args):
        return self

    def insert(self, data):
        self._data = data
        self._single_mode = False
        return self

    def single(self):
        self._single_mode = True
        return self

    def execute(self):
        if self._single_mode:
            if isinstance(self._data, list):
                return MockQueryResponse(self._data[0] if self._data else None)
            return MockQueryResponse(self._data)
        return MockQueryResponse(self._data)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def service(mock_db):
    return MessagingService(mock_db)


@pytest.mark.asyncio
async def test_get_or_create_conversation_returns_inserted_dict(service, mock_db):
    query = MockQueryBuilder([])
    mock_db.table.return_value = query

    result = await service.get_or_create_conversation("user-1", "user-2", "idea-1")

    assert result["participant_1"] == "user-1"
    assert result["participant_2"] == "user-2"
    assert result["idea_id"] == "idea-1"
    assert result["conversation_id"]


@pytest.mark.asyncio
async def test_get_or_create_conversation_rejects_self(service):
    with pytest.raises(ValueError, match="cannot start a conversation with yourself"):
        await service.get_or_create_conversation("user-1", "user-1")


@pytest.mark.asyncio
async def test_get_idea_owner_can_message_when_published_and_not_owner(mock_db):
    idea_builder = MockQueryBuilder({"user_id": "owner-1", "title": "T", "is_published": True})
    user_builder = MockQueryBuilder({"user_id": "owner-1", "username": "founder"})

    def table_side_effect(name):
        if name == "ideas":
            return idea_builder
        if name == "users":
            return user_builder
        raise AssertionError(name)

    mock_db.table.side_effect = table_side_effect
    service = MessagingService(mock_db)

    out = await service.get_idea_owner("idea-1", "viewer-1")
    assert out is not None
    assert out["can_message"] is True
    assert out["is_published"] is True


@pytest.mark.asyncio
async def test_get_idea_owner_no_can_message_for_owner_even_if_published(mock_db):
    idea_builder = MockQueryBuilder({"user_id": "owner-1", "title": "T", "is_published": True})
    user_builder = MockQueryBuilder({"user_id": "owner-1", "username": "founder"})

    def table_side_effect(name):
        if name == "ideas":
            return idea_builder
        if name == "users":
            return user_builder
        raise AssertionError(name)

    mock_db.table.side_effect = table_side_effect
    service = MessagingService(mock_db)

    out = await service.get_idea_owner("idea-1", "owner-1")
    assert out is not None
    assert out["can_message"] is False


@pytest.mark.asyncio
async def test_send_message_returns_inserted_dict(service, mock_db):
    conversation_query = MockQueryBuilder(
        {
            "conversation_id": "conv-1",
            "participant_1": "user-1",
            "participant_2": "user-2",
        }
    )
    messages_query = MockQueryBuilder()

    def table_side_effect(name):
        if name == "conversations":
            return conversation_query
        if name == "messages":
            return messages_query
        raise AssertionError(f"Unexpected table lookup: {name}")

    mock_db.table.side_effect = table_side_effect

    result = await service.send_message("conv-1", "user-1", "Hello there")

    assert result["conversation_id"] == "conv-1"
    assert result["sender_id"] == "user-1"
    assert result["content"] == "Hello there"
    assert result["message_id"]
