"""GraphQL wiring for the Phase 3 generation-job queue: enqueueBackgroundTasks
mutation + generationJob status query (mocked auth, in-memory DB)."""

from unittest.mock import MagicMock, patch

import pytest
from app.db.database import InMemoryDatabaseClient


def _info(db):
    info = MagicMock()
    info.context = {"db": db, "request": MagicMock()}
    return info


@pytest.mark.asyncio
async def test_enqueue_then_poll_status():
    db = InMemoryDatabaseClient()
    info = _info(db)
    with patch("app.graphql.resolvers.documents.get_current_user_id", return_value="user-1"):
        from app.graphql.schema import Mutation, Query

        result = await Mutation().enqueue_background_tasks(
            info, idea_id="idea-1", document_types=["pitch_deck", "prd"]
        )
        assert result.status == "queued"
        assert result.job_id

        job = await Query().generation_job(info, job_id=result.job_id)
        assert job is not None
        assert job.status == "queued"
        assert job.document_types == ["pitch_deck", "prd"]
        assert job.idea_id == "idea-1"


@pytest.mark.asyncio
async def test_enqueue_is_idempotent():
    db = InMemoryDatabaseClient()
    info = _info(db)
    with patch("app.graphql.resolvers.documents.get_current_user_id", return_value="user-1"):
        from app.graphql.schema import Mutation

        r1 = await Mutation().enqueue_background_tasks(
            info, idea_id="i1", document_types=["prd"], idempotency_key="dedupe-key"
        )
        r2 = await Mutation().enqueue_background_tasks(
            info, idea_id="i1", document_types=["prd"], idempotency_key="dedupe-key"
        )
    assert r1.job_id == r2.job_id


@pytest.mark.asyncio
async def test_generation_job_ownership_enforced():
    db = InMemoryDatabaseClient()
    info = _info(db)
    with patch("app.graphql.resolvers.documents.get_current_user_id", return_value="owner"):
        from app.graphql.schema import Mutation

        created = await Mutation().enqueue_background_tasks(
            info, idea_id="i1", document_types=["prd"]
        )
    with patch("app.graphql.resolvers.documents.get_current_user_id", return_value="intruder"):
        from app.graphql.schema import Query

        assert await Query().generation_job(info, job_id=created.job_id) is None


@pytest.mark.asyncio
async def test_generation_job_missing_returns_none():
    db = InMemoryDatabaseClient()
    info = _info(db)
    with patch("app.graphql.resolvers.documents.get_current_user_id", return_value="u"):
        from app.graphql.schema import Query

        assert await Query().generation_job(info, job_id="does-not-exist") is None
