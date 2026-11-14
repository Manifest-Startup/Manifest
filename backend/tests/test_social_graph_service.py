"""
Tests for Social Graph Service
"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime
from app.services.social.graph import SocialGraphService, create_social_graph_service


def create_mock_db():
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_response = MagicMock()
    
    mock_db.table.return_value = mock_query
    mock_query.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.in_.return_value = mock_query
    mock_query.neq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.single.return_value = mock_query
    mock_query.upsert.return_value = mock_query
    mock_query.insert.return_value = mock_query
    mock_query.update.return_value = mock_query
    mock_query.delete.return_value = mock_query
    mock_query.execute.return_value = mock_response
    
    return mock_db, mock_query, mock_response


@pytest.fixture
def mock_db():
    db, _, _ = create_mock_db()
    return db


@pytest.fixture
def social_service(mock_db):
    return SocialGraphService(mock_db)


class TestSocialGraphService:
    @pytest.mark.asyncio
    async def test_follow_user(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = {
            "follow_id": "follow-123",
            "follower_id": "user-1",
            "followed_id": "user-2",
            "created_at": datetime.utcnow().isoformat()
        }

        service = SocialGraphService(mock_db)
        result = await service.follow_user("user-1", "user-2")

        assert result["follow_id"] == "follow-123"
        assert result["follower_id"] == "user-1"
        assert result["followed_id"] == "user-2"

    @pytest.mark.asyncio
    async def test_follow_self_raises_error(self, social_service):
        with pytest.raises(ValueError, match="Cannot follow yourself"):
            await social_service.follow_user("user-1", "user-1")

    @pytest.mark.asyncio
    async def test_unfollow_user(self, social_service, mock_db):
        mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()

        result = await social_service.unfollow_user("user-1", "user-2")

        assert result is True

    @pytest.mark.asyncio
    async def test_toggle_follow_when_not_following(self):
        mock_db, mock_query, mock_response = create_mock_db()
        service = SocialGraphService(mock_db)
        
        call_count = [0]
        def mock_execute():
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(data=[])
            else:
                return MagicMock(data={"follow_id": "f-1"})
        
        mock_query.execute.side_effect = mock_execute
        
        result = await service.toggle_follow("user-1", "user-2")
        assert result["followed_id"] == "user-2"

    @pytest.mark.asyncio
    async def test_toggle_follow_when_already_following(self):
        mock_db, mock_query, mock_response = create_mock_db()
        service = SocialGraphService(mock_db)
        
        call_count = [0]
        def mock_execute():
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(data=[{"follow_id": "f-1"}])
            else:
                return MagicMock(data=[])
        
        mock_query.execute.side_effect = mock_execute
        
        result = await service.toggle_follow("user-1", "user-2")
        assert result["followed_id"] == "user-2"

    @pytest.mark.asyncio
    async def test_is_following_true(self, social_service, mock_db):
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"follow_id": "f-1"}])

        result = await social_service.is_following("user-1", "user-2")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_following_false(self, social_service, mock_db):
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        result = await social_service.is_following("user-1", "user-2")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_followers(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = [
            {"follow_id": "f-1", "follower_id": "user-2"},
            {"follow_id": "f-2", "follower_id": "user-3"}
        ]

        service = SocialGraphService(mock_db)
        result = await service.get_followers("user-1")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_following(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = [
            {"follow_id": "f-1", "followed_id": "user-2"},
            {"follow_id": "f-2", "followed_id": "user-3"}
        ]

        service = SocialGraphService(mock_db)
        result = await service.get_following("user-1")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_follower_count(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = [
            {"follow_id": "f-1"},
            {"follow_id": "f-2"},
            {"follow_id": "f-3"}
        ]

        service = SocialGraphService(mock_db)
        result = await service.get_follower_count("user-1")

        assert result == 3

    @pytest.mark.asyncio
    async def test_get_following_count(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = [
            {"follow_id": "f-1"},
            {"follow_id": "f-2"}
        ]

        service = SocialGraphService(mock_db)
        result = await service.get_following_count("user-1")

        assert result == 2

    @pytest.mark.asyncio
    async def test_get_follower_counts(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = [
            {"followed_id": "user-1"},
            {"followed_id": "user-1"},
            {"followed_id": "user-2"},
        ]

        service = SocialGraphService(mock_db)
        result = await service.get_follower_counts(["user-1", "user-2", "user-3"])

        assert result == {"user-1": 2, "user-2": 1, "user-3": 0}

    @pytest.mark.asyncio
    async def test_get_following_set(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = [
            {"followed_id": "creator-1"},
            {"followed_id": "creator-3"},
        ]

        service = SocialGraphService(mock_db)
        result = await service.get_following_set("viewer-1", ["creator-1", "creator-2", "creator-3"])

        assert result == {"creator-1", "creator-3"}

    @pytest.mark.asyncio
    async def test_upvote_idea(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = {
            "vote_id": "vote-123",
            "idea_id": "idea-1",
            "user_id": "user-1"
        }

        service = SocialGraphService(mock_db)
        result = await service.upvote_idea("idea-1", "user-1")

        assert result["vote_id"] == "vote-123"

    @pytest.mark.asyncio
    async def test_get_idea_vote_count(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = [
            {"vote_id": "v-1"},
            {"vote_id": "v-2"},
            {"vote_id": "v-3"}
        ]

        service = SocialGraphService(mock_db)
        result = await service.get_idea_vote_count("idea-1")

        assert result == 3


class TestCreateSocialGraphServiceFactory:
    def test_create_social_graph_service(self):
        mock_db = MagicMock()
        service = create_social_graph_service(mock_db)
        
        assert isinstance(service, SocialGraphService)
        assert service.db == mock_db


class TestSocialGraphServiceEdgeCases:
    @pytest.mark.asyncio
    async def test_get_empty_followers(self, social_service, mock_db):
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[])

        result = await social_service.get_followers("user-no-followers")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_empty_following(self, social_service, mock_db):
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[])

        result = await social_service.get_following("user-not-following")

        assert result == []
