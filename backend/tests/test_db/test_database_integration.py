import pytest
import os
import uuid
from datetime import datetime
from app.db.database import DatabaseClient, create_database_client, get_db_connection


@pytest.fixture
def db_client():
    return create_database_client()


@pytest.fixture
def test_user_id():
    return str(uuid.uuid4())


@pytest.fixture
def cleanup_test_data(db_client, test_user_id):
    yield
    try:
        db_client.table("ideas").eq("user_id", test_user_id).delete().execute()
        db_client.table("users").eq("user_id", test_user_id).delete().execute()
    except Exception:
        pass


@pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION_TESTS") != "1" or not os.getenv("DATABASE_URL"),
    reason="set RUN_DB_INTEGRATION_TESTS=1 and DATABASE_URL to run database integration tests"
)
class TestDatabaseIntegration:
    def test_connection(self, db_client):
        result = db_client.execute_raw("SELECT 1 as test")
        assert result.data is not None
        assert result.data[0]["test"] == 1

    def test_insert_and_select_user(self, db_client, test_user_id, cleanup_test_data):
        user_data = {
            "user_id": test_user_id,
            "email": f"test_{test_user_id[:8]}@example.com",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        insert_result = db_client.table("users").insert(user_data).execute()
        assert insert_result.data is not None
        assert insert_result.data["user_id"] == test_user_id

        select_result = db_client.table("users").select().eq("user_id", test_user_id).single().execute()
        assert select_result.data is not None
        assert select_result.data["email"] == user_data["email"]

    def test_update_user(self, db_client, test_user_id, cleanup_test_data):
        user_data = {
            "user_id": test_user_id,
            "email": f"test_{test_user_id[:8]}@example.com",
            "created_at": datetime.utcnow().isoformat(),
        }
        db_client.table("users").insert(user_data).execute()

        update_result = db_client.table("users").update({
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User"
        }).eq("user_id", test_user_id).execute()

        assert update_result.data is not None

        select_result = db_client.table("users").select().eq("user_id", test_user_id).single().execute()
        assert select_result.data["username"] == "testuser"
        assert select_result.data["first_name"] == "Test"

    def test_upsert_user(self, db_client, test_user_id, cleanup_test_data):
        user_data = {
            "user_id": test_user_id,
            "email": f"test_{test_user_id[:8]}@example.com",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        upsert_result = db_client.table("users").upsert(user_data, on_conflict="user_id").execute()
        assert upsert_result.data is not None

        user_data["username"] = "updated_user"
        upsert_result2 = db_client.table("users").upsert(user_data, on_conflict="user_id").execute()
        
        select_result = db_client.table("users").select().eq("user_id", test_user_id).single().execute()
        assert select_result.data["username"] == "updated_user"

    def test_delete_user(self, db_client, test_user_id):
        user_data = {
            "user_id": test_user_id,
            "email": f"test_{test_user_id[:8]}@example.com",
            "created_at": datetime.utcnow().isoformat(),
        }
        db_client.table("users").insert(user_data).execute()

        delete_result = db_client.table("users").eq("user_id", test_user_id).delete().execute()
        assert delete_result.data is not None

        select_result = db_client.table("users").select().eq("user_id", test_user_id).single().execute()
        assert select_result.data is None

    def test_select_with_ordering(self, db_client, test_user_id, cleanup_test_data):
        user_data = {
            "user_id": test_user_id,
            "email": f"test_{test_user_id[:8]}@example.com",
            "created_at": datetime.utcnow().isoformat(),
        }
        db_client.table("users").insert(user_data).execute()

        result = db_client.table("users").select().order("created_at", desc=True).limit(5).execute()
        assert isinstance(result.data, list)

    def test_select_with_multiple_filters(self, db_client, test_user_id, cleanup_test_data):
        user_data = {
            "user_id": test_user_id,
            "email": f"test_{test_user_id[:8]}@example.com",
            "username": "filtertest",
            "created_at": datetime.utcnow().isoformat(),
        }
        db_client.table("users").insert(user_data).execute()

        result = db_client.table("users").select().eq("user_id", test_user_id).eq("username", "filtertest").execute()
        assert len(result.data) == 1

    def test_idea_crud_operations(self, db_client, test_user_id, cleanup_test_data):
        user_data = {
            "user_id": test_user_id,
            "email": f"test_{test_user_id[:8]}@example.com",
            "created_at": datetime.utcnow().isoformat(),
        }
        db_client.table("users").insert(user_data).execute()

        idea_id = str(uuid.uuid4())
        idea_data = {
            "idea_id": idea_id,
            "user_id": test_user_id,
            "title": "Test Idea",
            "description": "This is a test idea",
            "created_at": datetime.utcnow().isoformat(),
        }
        insert_result = db_client.table("ideas").insert(idea_data).execute()
        assert insert_result.data is not None
        assert insert_result.data["title"] == "Test Idea"

        select_result = db_client.table("ideas").select().eq("idea_id", idea_id).single().execute()
        assert select_result.data["description"] == "This is a test idea"

        update_result = db_client.table("ideas").update({"title": "Updated Idea"}).eq("idea_id", idea_id).execute()
        assert update_result.data is not None

        db_client.table("ideas").eq("idea_id", idea_id).delete().execute()

    def test_delete_idea_cascades_generated_artifacts_and_pitch_comments(self, db_client, test_user_id):
        user_data = {
            "user_id": test_user_id,
            "email": f"cascade_{test_user_id[:8]}@example.com",
            "created_at": datetime.utcnow().isoformat(),
        }
        db_client.table("users").insert(user_data).execute()

        idea_id = str(uuid.uuid4())
        db_client.table("ideas").insert({
            "idea_id": idea_id,
            "user_id": test_user_id,
            "title": "Idea with generated artifacts",
            "description": "Used to verify cascading delete behavior",
            "created_at": datetime.utcnow().isoformat(),
        }).execute()

        pitch_id = None
        try:
            pitch_result = db_client.table("pitch_decks").insert({
                "idea_id": idea_id,
                "user_id": test_user_id,
                "description": "Generated pitch deck",
            }).execute()
            pitch_id = pitch_result.data["pitch_id"]

            db_client.table("product_requirements_documents").insert({
                "idea_id": idea_id,
                "user_id": test_user_id,
                "description": "Generated PRD",
            }).execute()

            db_client.table("intellectual_properties").insert({
                "idea_id": idea_id,
                "user_id": test_user_id,
                "type": "provisional_patent",
                "title_of_invention": "Generated patent package",
            }).execute()

            db_client.table("comments").insert({
                "idea_id": idea_id,
                "user_id": test_user_id,
                "content": "Direct idea comment",
            }).execute()
            db_client.table("comments").insert({
                "pitch_id": pitch_id,
                "user_id": test_user_id,
                "content": "Pitch deck comment",
            }).execute()

            delete_result = db_client.table("ideas").eq("idea_id", idea_id).delete().execute()
            assert delete_result.data is not None
            assert len(delete_result.data) == 1
            assert delete_result.data[0]["idea_id"] == idea_id

            assert db_client.table("ideas").select().eq("idea_id", idea_id).single().execute().data is None
            assert db_client.table("pitch_decks").select().eq("idea_id", idea_id).execute().data == []
            assert db_client.table("product_requirements_documents").select().eq("idea_id", idea_id).execute().data == []
            assert db_client.table("intellectual_properties").select().eq("idea_id", idea_id).execute().data == []
            assert db_client.table("comments").select().eq("idea_id", idea_id).execute().data == []
            assert db_client.table("comments").select().eq("pitch_id", pitch_id).execute().data == []
        finally:
            if pitch_id:
                db_client.table("comments").eq("pitch_id", pitch_id).delete().execute()
            db_client.table("comments").eq("idea_id", idea_id).delete().execute()
            db_client.table("product_requirements_documents").eq("idea_id", idea_id).delete().execute()
            db_client.table("intellectual_properties").eq("idea_id", idea_id).delete().execute()
            db_client.table("pitch_decks").eq("idea_id", idea_id).delete().execute()
            db_client.table("ideas").eq("idea_id", idea_id).delete().execute()
            db_client.table("users").eq("user_id", test_user_id).delete().execute()

    def test_ilike_search(self, db_client, test_user_id, cleanup_test_data):
        user_data = {
            "user_id": test_user_id,
            "email": f"searchtest_{test_user_id[:8]}@example.com",
            "created_at": datetime.utcnow().isoformat(),
        }
        db_client.table("users").insert(user_data).execute()

        result = db_client.table("users").select().ilike("email", f"%{test_user_id[:8]}%").execute()
        assert len(result.data) >= 1

    def test_execute_raw_query(self, db_client):
        result = db_client.execute_raw("SELECT NOW() as current_time")
        assert result.data is not None
        assert "current_time" in result.data[0]

    def test_execute_raw_with_params(self, db_client, test_user_id, cleanup_test_data):
        user_data = {
            "user_id": test_user_id,
            "email": f"test_{test_user_id[:8]}@example.com",
            "created_at": datetime.utcnow().isoformat(),
        }
        db_client.table("users").insert(user_data).execute()

        result = db_client.execute_raw(
            "SELECT * FROM users WHERE user_id = %s",
            (test_user_id,)
        )
        assert len(result.data) == 1
        assert result.data[0]["user_id"] == test_user_id
