"""GraphQL tests for import/export mutations."""
import base64
import io
import json
import os
import sys
import zipfile
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from app.main import app
from app.db.database import InMemoryDatabaseClient, set_db_client_override


EXPORT_IDEAS_MUTATION = """
mutation ExportIdeas($format: String!) {
    exportIdeas(format: $format) {
        content
        format
        filename
    }
}
"""

GET_IDEAS_QUERY = """
query GetIdeas {
    ideas {
        ideaId
        title
    }
}
"""

IMPORT_IDEAS_MUTATION = """
mutation ImportIdeas($fileContent: String!, $fileFormat: String!, $filename: String!) {
    importIdeas(fileContent: $fileContent, fileFormat: $fileFormat, filename: $filename) {
        importedCount
        skippedCount
        errors
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
    # Bulk export now requires recent auth (step-up MFA OR fresh login).
    # In unit tests there is no real session, so short-circuit the helper.
    with patch("app.graphql.schema.get_current_user_id", return_value="test_user_id"), \
         patch("app.graphql.resolvers.ideas.get_current_user_id", return_value="test_user_id"), \
         patch("app.security.step_up._recent_login_satisfies", return_value=True):
        yield


def graphql_post(query: str, variables: dict):
    return client.post("/graphql", json={"query": query, "variables": variables})


def seed_idea(db: InMemoryDatabaseClient, title: str = "Seed Idea"):
    db.table("ideas").insert(
        {
            "idea_id": "idea-1",
            "user_id": "test_user_id",
            "title": title,
            "description": "Description",
            "summary": "Summary",
            "tags": "tag1",
            "created_at": "2024-01-01T00:00:00",
        }
    ).execute()


class TestExportIdeas:
    def test_export_ideas_json(self, in_memory_db, mock_get_current_user_id):
        seed_idea(in_memory_db)
        response = graphql_post(EXPORT_IDEAS_MUTATION, {"format": "json"})
        result = response.json()
        assert response.status_code == 200
        assert "errors" not in result
        assert result["data"]["exportIdeas"]["format"] == "json"
        assert result["data"]["exportIdeas"]["filename"].endswith(".json")

        content = base64.b64decode(result["data"]["exportIdeas"]["content"]).decode("utf-8")
        data = json.loads(content)
        assert len(data["ideas"]) == 1
        assert data["ideas"][0]["title"] == "Seed Idea"

    def test_export_ideas_csv(self, in_memory_db, mock_get_current_user_id):
        seed_idea(in_memory_db)
        response = graphql_post(EXPORT_IDEAS_MUTATION, {"format": "csv"})
        result = response.json()
        assert response.status_code == 200
        assert "errors" not in result
        assert result["data"]["exportIdeas"]["format"] == "csv"
        assert result["data"]["exportIdeas"]["filename"].endswith(".csv")

    def test_export_ideas_markdown(self, in_memory_db, mock_get_current_user_id):
        seed_idea(in_memory_db)
        response = graphql_post(EXPORT_IDEAS_MUTATION, {"format": "markdown"})
        result = response.json()
        assert response.status_code == 200
        assert "errors" not in result
        assert result["data"]["exportIdeas"]["format"] == "markdown"
        assert result["data"]["exportIdeas"]["filename"].endswith(".md")

    def test_export_ideas_no_ideas(self, in_memory_db, mock_get_current_user_id):
        response = graphql_post(EXPORT_IDEAS_MUTATION, {"format": "json"})
        result = response.json()
        assert response.status_code == 200
        assert "errors" in result
        assert "No ideas found" in result["errors"][0]["message"]

    def test_export_ideas_invalid_format(self, in_memory_db, mock_get_current_user_id):
        seed_idea(in_memory_db)
        response = graphql_post(EXPORT_IDEAS_MUTATION, {"format": "invalid"})
        result = response.json()
        assert response.status_code == 200
        assert "errors" in result
        assert "Unsupported export format" in result["errors"][0]["message"]


class TestImportIdeas:
    def test_import_ideas_json(self, in_memory_db, mock_get_current_user_id):
        json_data = json.dumps(
            {
                "ideas": [
                    {"title": "Imported Idea 1", "description": "Desc 1", "summary": "Sum 1", "tags": "tag1"},
                    {"title": "Imported Idea 2", "description": "Desc 2", "summary": "Sum 2", "tags": "tag2"},
                ]
            }
        )
        file_content = base64.b64encode(json_data.encode("utf-8")).decode("utf-8")

        response = graphql_post(
            IMPORT_IDEAS_MUTATION,
            {"fileContent": file_content, "fileFormat": "json", "filename": "test.json"},
        )
        result = response.json()
        assert response.status_code == 200
        assert "errors" not in result
        assert result["data"]["importIdeas"]["importedCount"] == 2
        assert result["data"]["importIdeas"]["skippedCount"] == 0

        rows = in_memory_db.table("ideas").select("*").execute().data
        assert len(rows) == 2
        assert all(row.get("idea_id") for row in rows)

    def test_import_ideas_csv(self, in_memory_db, mock_get_current_user_id):
        csv_data = "title,description,summary,tags\nIdea 1,Desc 1,Sum 1,tag1\nIdea 2,Desc 2,Sum 2,tag2"
        file_content = base64.b64encode(csv_data.encode("utf-8")).decode("utf-8")

        response = graphql_post(
            IMPORT_IDEAS_MUTATION,
            {"fileContent": file_content, "fileFormat": "csv", "filename": "test.csv"},
        )
        result = response.json()
        assert response.status_code == 200
        assert "errors" not in result
        assert result["data"]["importIdeas"]["importedCount"] >= 1

    def test_import_ideas_invalid_format(self, in_memory_db, mock_get_current_user_id):
        payload = base64.b64encode(b"plain text").decode("utf-8")
        response = graphql_post(
            IMPORT_IDEAS_MUTATION,
            {"fileContent": payload, "fileFormat": "bin", "filename": "test.bin"},
        )
        result = response.json()
        assert response.status_code == 200
        assert "errors" in result
        assert "Unsupported import format" in result["errors"][0]["message"]

    def test_import_google_keep_archive_filters_non_ideas(self, in_memory_db, mock_get_current_user_id):
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr(
                "Takeout/Keep/Factory copilot.json",
                json.dumps(
                    {
                        "title": "Factory copilot",
                        "textContent": "Startup idea for software that automates compliance and maintenance workflows in factories.",
                        "labels": ["ops"],
                    }
                ),
            )
            archive.writestr(
                "Takeout/Keep/Groceries.json",
                json.dumps({"title": "Groceries", "textContent": "milk, eggs, bananas"}),
            )

        file_content = base64.b64encode(archive_bytes.getvalue()).decode("utf-8")
        response = graphql_post(
            IMPORT_IDEAS_MUTATION,
            {"fileContent": file_content, "fileFormat": "zip", "filename": "keep-export.zip"},
        )
        result = response.json()

        assert response.status_code == 200
        assert "errors" not in result
        assert result["data"]["importIdeas"]["importedCount"] == 1
        assert result["data"]["importIdeas"]["skippedCount"] == 1

        rows = in_memory_db.table("ideas").select("*").execute().data
        assert len(rows) == 1
        assert rows[0]["title"] == "Factory copilot"

    def test_import_skips_duplicate_ideas(self, in_memory_db, mock_get_current_user_id):
        seed_idea(in_memory_db, title="Factory copilot")
        in_memory_db.table("ideas").update({"description": "Startup idea for software that automates compliance and maintenance workflows in factories."}).eq("idea_id", "idea-1").execute()

        json_data = json.dumps(
            [
                {
                    "title": "Factory copilot",
                    "description": "Startup idea for software that automates compliance and maintenance workflows in factories.",
                }
            ]
        )
        file_content = base64.b64encode(json_data.encode("utf-8")).decode("utf-8")

        response = graphql_post(
            IMPORT_IDEAS_MUTATION,
            {"fileContent": file_content, "fileFormat": "json", "filename": "duplicate.json"},
        )
        result = response.json()

        assert response.status_code == 200
        assert "errors" not in result
        assert result["data"]["importIdeas"]["importedCount"] == 0
        assert result["data"]["importIdeas"]["skippedCount"] == 1

    def test_ideas_query_backfills_missing_idea_ids(self, in_memory_db, mock_get_current_user_id):
        in_memory_db.table("ideas").insert(
            {
                "title": "Fitness App",
                "description": "Apple Notes import about an AI fitness and health planning product.",
                "user_id": "test_user_id",
                "created_at": "2026-03-15T10:00:00",
            }
        ).execute()

        response = graphql_post(GET_IDEAS_QUERY, {})
        result = response.json()

        assert response.status_code == 200
        assert "errors" not in result
        assert result["data"]["ideas"][0]["title"] == "Fitness App"
        assert result["data"]["ideas"][0]["ideaId"]

        rows = in_memory_db.table("ideas").select("*").execute().data
        assert rows[0]["idea_id"]
