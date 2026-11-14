import sys
import time
from types import SimpleNamespace

import pytest

from app.db.database import InMemoryDatabaseClient, begin_query_metrics, end_query_metrics
from app.graphql.schema import Query
from app.services.social.investments import InvestmentService
from app.services.social.messaging import MessagingService
from app.services.social.graph import SocialGraphService


def _seed_users(store, count=60):
    store["users"] = [
        {
            "user_id": f"user-{idx}",
            "email": f"user-{idx}@example.com",
            "first_name": f"User{idx}",
            "last_name": "Example",
            "username": f"user{idx}",
            "profile_picture_url": None,
        }
        for idx in range(count)
    ]


def _measure_queries():
    token = begin_query_metrics()
    return token


def _finish_queries(token):
    return end_query_metrics(token)


def test_database_pool_is_reused_for_postgres_connections(monkeypatch):
    import app.db.database as database

    class FakePool:
        instances = 0

        def __init__(self, *args, **kwargs):
            FakePool.instances += 1
            self.getconn_count = 0

        def getconn(self):
            self.getconn_count += 1
            return object()

    monkeypatch.setenv("DB_POOL_ENABLED", "1")
    monkeypatch.setattr(database, "ThreadedConnectionPool", FakePool)
    monkeypatch.setattr(database, "_db_pool", None)

    first_conn, first_from_pool = database._get_pooled_connection("postgres://example")
    second_conn, second_from_pool = database._get_pooled_connection("postgres://example")

    assert first_conn is not second_conn
    assert first_from_pool is True
    assert second_from_pool is True
    assert FakePool.instances == 1
    assert database._db_pool.getconn_count == 2


@pytest.mark.asyncio
async def test_messaging_conversations_have_constant_lookup_budget():
    store = {}
    _seed_users(store)
    store["ideas"] = [{"idea_id": f"idea-{idx}", "title": f"Idea {idx}"} for idx in range(50)]
    store["conversations"] = [
        {
            "conversation_id": f"conversation-{idx}",
            "participant_1": "user-0",
            "participant_2": f"user-{idx + 1}",
            "idea_id": f"idea-{idx}",
            "last_message_at": f"2026-04-25T00:{idx:02d}:00",
            "participant_1_unread_count": 0,
            "participant_2_unread_count": 0,
        }
        for idx in range(50)
    ]
    service = MessagingService(InMemoryDatabaseClient(store))

    token = _measure_queries()
    conversations = await service.get_user_conversations("user-0", limit=50, offset=0)
    metrics = _finish_queries(token)

    assert len(conversations) == 50
    assert metrics["query_count"] <= 3


@pytest.mark.asyncio
async def test_conversation_messages_batch_sender_profiles():
    store = {}
    _seed_users(store)
    store["conversations"] = [
        {
            "conversation_id": "conversation-1",
            "participant_1": "user-0",
            "participant_2": "user-1",
            "idea_id": None,
        }
    ]
    store["messages"] = [
        {
            "message_id": f"message-{idx}",
            "conversation_id": "conversation-1",
            "sender_id": f"user-{idx % 10}",
            "content": "hello",
            "created_at": f"2026-04-25T00:{idx:02d}:00",
        }
        for idx in range(50)
    ]
    service = MessagingService(InMemoryDatabaseClient(store))

    token = _measure_queries()
    messages = await service.get_conversation_messages("conversation-1", "user-0", limit=50)
    metrics = _finish_queries(token)

    assert len(messages) == 50
    assert metrics["query_count"] <= 3


@pytest.mark.asyncio
async def test_social_followers_batch_profiles():
    store = {}
    _seed_users(store)
    store["user_follows"] = [
        {"follow_id": f"follow-{idx}", "follower_id": f"user-{idx}", "followed_id": "user-0", "created_at": idx}
        for idx in range(1, 51)
    ]
    service = SocialGraphService(InMemoryDatabaseClient(store))

    token = _measure_queries()
    followers = await service.get_followers("user-0")
    metrics = _finish_queries(token)

    assert len(followers) == 50
    assert metrics["query_count"] <= 2


@pytest.mark.asyncio
async def test_investments_batch_investor_profiles():
    store = {}
    _seed_users(store)
    store["investments"] = [
        {
            "investment_id": f"investment-{idx}",
            "idea_id": "idea-1",
            "investor_id": f"user-{idx}",
            "created_at": idx,
        }
        for idx in range(1, 51)
    ]
    service = InvestmentService(InMemoryDatabaseClient(store))

    token = _measure_queries()
    investments = await service.get_idea_investments("idea-1")
    metrics = _finish_queries(token)

    assert len(investments) == 50
    assert metrics["query_count"] <= 2


@pytest.mark.asyncio
async def test_find_similar_ideas_latency_is_ai_delay_plus_small_overhead(monkeypatch):
    class FakeAiLayer:
        @staticmethod
        def is_available():
            return True

    class FakeSimilarIdeas:
        @staticmethod
        def update():
            time.sleep(0.05)

    fake_manager = SimpleNamespace(
        ai_layer=FakeAiLayer(),
        similar_ideas=FakeSimilarIdeas(),
        set_idea=lambda description: None,
        get_similar_ideas=lambda: "cached similar ideas",
    )
    monkeypatch.setattr("app.managers.manifest_manager.manifest_manager", fake_manager)

    query = Query()
    description = f"latency test idea {time.time_ns()}"

    started = time.perf_counter()
    first = await query.find_similar_ideas(SimpleNamespace(context={}), description)
    first_duration = time.perf_counter() - started

    started = time.perf_counter()
    second = await query.find_similar_ideas(SimpleNamespace(context={}), description)
    cached_duration = time.perf_counter() - started

    assert first.similar_ideas == "cached similar ideas"
    assert second.similar_ideas == "cached similar ideas"
    assert first_duration < 0.15
    assert cached_duration < 0.02
