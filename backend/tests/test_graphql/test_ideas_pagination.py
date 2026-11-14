"""Stage #3 — ideas list pagination and denormalized metadata."""

import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from app.main import app
from app.db.database import InMemoryDatabaseClient, set_db_client_override
from app.services.idea_list_metadata_service import encode_ideas_cursor


GET_IDEAS_PAGE = """
query GetIdeas($first: Int, $after: String) {
    ideas(first: $first, after: $after) {
        ideaId
        title
        generatedAssetCount
        hasDescription
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


def _insert_idea(db, idea_id: str, title: str, *, created_at: datetime, asset_count: int = 0):
    db.table("ideas").insert(
        {
            "idea_id": idea_id,
            "user_id": "test_user_id",
            "title": title,
            "description": "Desc" if asset_count else "",
            "created_at": created_at.isoformat(),
            "is_published": False,
            "generated_asset_count": asset_count,
            "has_description": bool(asset_count),
        }
    ).execute()


def test_ideas_respects_first_limit(in_memory_db, mock_get_current_user_id):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for idx in range(5):
        _insert_idea(
            in_memory_db,
            f"idea-{idx}",
            f"Idea {idx}",
            created_at=base + timedelta(hours=idx),
            asset_count=idx % 2,
        )

    response = client.post(
        "/graphql",
        json={"query": GET_IDEAS_PAGE, "variables": {"first": 2}},
    )
    body = response.json()

    assert response.status_code == 200
    assert "errors" not in body
    rows = body["data"]["ideas"]
    assert len(rows) == 2
    assert rows[0]["title"] == "Idea 4"
    assert rows[1]["title"] == "Idea 3"


def test_ideas_supports_after_cursor(in_memory_db, mock_get_current_user_id):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    timestamps = [base + timedelta(hours=idx) for idx in range(4)]
    for idx, ts in enumerate(timestamps):
        _insert_idea(in_memory_db, f"idea-{idx}", f"Idea {idx}", created_at=ts)

    cursor = encode_ideas_cursor(timestamps[2], "idea-2")
    response = client.post(
        "/graphql",
        json={"query": GET_IDEAS_PAGE, "variables": {"first": 10, "after": cursor}},
    )
    body = response.json()

    assert response.status_code == 200
    assert "errors" not in body
    titles = [row["title"] for row in body["data"]["ideas"]]
    assert titles == ["Idea 1", "Idea 0"]


def test_ideas_rejects_invalid_cursor(in_memory_db, mock_get_current_user_id):
    _insert_idea(
        in_memory_db,
        "idea-1",
        "Only",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    response = client.post(
        "/graphql",
        json={"query": GET_IDEAS_PAGE, "variables": {"first": 5, "after": "not-a-cursor"}},
    )
    body = response.json()

    assert response.status_code == 200
    assert body.get("errors")
