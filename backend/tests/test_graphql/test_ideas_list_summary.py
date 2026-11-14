"""GraphQL tests for the lightweight ideas list (IdeaSummary)."""
import os
import sys
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from app.main import app
from app.db.database import InMemoryDatabaseClient, set_db_client_override


GET_IDEAS_SUMMARY = """
query GetIdeas {
    ideas {
        ideaId
        userId
        title
        hasDescription
        createdAt
        isPublished
        generatedAssetCount
    }
}
"""

client = TestClient(app)


@contextmanager
def _override_request_db(mock_db):
    import tests.conftest as shared_conftest

    sentinel = object()
    previous = getattr(shared_conftest, "mock_database_client", sentinel)
    shared_conftest.mock_database_client = mock_db
    try:
        yield
    finally:
        if previous is sentinel:
            delattr(shared_conftest, "mock_database_client")
        else:
            shared_conftest.mock_database_client = previous


@pytest.fixture
def in_memory_db():
    db = InMemoryDatabaseClient()
    with _override_request_db(db):
        set_db_client_override(db)
        yield db
    set_db_client_override(None)


@pytest.fixture
def mock_get_current_user_id():
    with patch("app.graphql.schema.get_current_user_id", return_value="test_user_id"):
        yield


def graphql_post(query: str, variables: dict | None = None):
    return client.post("/graphql", json={"query": query, "variables": variables or {}})


def test_ideas_returns_summary_with_generated_asset_count(in_memory_db, mock_get_current_user_id):
    in_memory_db.table("ideas").insert(
        {
            "idea_id": "idea-1",
            "user_id": "test_user_id",
            "title": "Alpha",
            "description": "Desc",
            "created_at": "2024-01-01T00:00:00",
            "is_published": False,
            "generated_asset_count": 2,
            "has_description": True,
            "pitch_deck": "# deck",
            "product_requirements_document": None,
            "provisional_patent": None,
            "business_model_canvas": "bmc",
        }
    ).execute()

    response = graphql_post(GET_IDEAS_SUMMARY, {})
    result = response.json()

    assert response.status_code == 200
    assert "errors" not in result
    row = result["data"]["ideas"][0]
    assert row["title"] == "Alpha"
    assert row["hasDescription"] is True
    assert row["generatedAssetCount"] == 2
