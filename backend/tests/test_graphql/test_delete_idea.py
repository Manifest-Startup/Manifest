import sys
import os
from types import SimpleNamespace
from typing import Optional
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from fastapi.testclient import TestClient
from app.main import app
import jwt
from app.auth.current_user import SUPABASE_JWT_SECRET, SUPABASE_URL

# A valid JWT token for testing
VALID_PAYLOAD = {
    "sub": "test_user_id",
    "aud": "authenticated",
    "iss": f"{SUPABASE_URL}/auth/v1"
}
VALID_TOKEN = jwt.encode(VALID_PAYLOAD, SUPABASE_JWT_SECRET, algorithm="HS256")

DELETE_IDEA_MUTATION = """
mutation DeleteIdea($ideaId: String!) {
    deleteIdea(ideaId: $ideaId)
}
"""

client = TestClient(app)

@pytest.fixture
def mock_supabase():
    """Mock DB client for GraphQL context.

    `app.main.get_context` reads `tests.conftest.mock_database_client` under
    pytest; without it the resolver uses `create_database_client()` (in-memory
    when DATABASE_URL is unset) and ignores the chained Mock below.
    """
    import tests.conftest as shared_conftest

    global_mock = shared_conftest.mock_supabase
    mock_table = Mock()
    global_mock.table.return_value = mock_table
    sentinel = object()
    previous = getattr(shared_conftest, "mock_database_client", sentinel)
    shared_conftest.mock_database_client = global_mock
    yield global_mock
    if previous is sentinel:
        delattr(shared_conftest, "mock_database_client")
    else:
        shared_conftest.mock_database_client = previous

@pytest.fixture
def mock_get_current_user_id():
    """Mock get_current_user_id to return a test user ID."""
    with patch('app.graphql.schema.get_current_user_id', return_value='test_user_id'):
        yield

def test_delete_idea_success(mock_supabase, mock_get_current_user_id):
    """Test successful deletion of an idea."""
    idea_id = "test_idea_id"
    
    # Mock the check query chain to verify idea exists
    mock_check_response = Mock()
    mock_check_response.data = [{"idea_id": idea_id}]
    
    # Mock the delete query chain
    mock_delete_response = Mock()
    mock_delete_response.data = [{"idea_id": idea_id}]  # Supabase returns deleted rows
    
    # Setup the mock chain for check (select().eq().eq().single().execute())
    mock_select = Mock()
    mock_eq1 = Mock()
    mock_eq2 = Mock()
    mock_single = Mock()
    mock_table = mock_supabase.table.return_value
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq1
    mock_eq1.eq.return_value = mock_eq2
    mock_eq2.limit.return_value = mock_single
    mock_single.execute.return_value = mock_check_response
    
    # Setup the mock chain for delete (delete().eq().eq().execute())
    mock_delete = Mock()
    mock_delete_eq1 = Mock()
    mock_delete_eq2 = Mock()
    mock_table.delete.return_value = mock_delete
    mock_delete.eq.return_value = mock_delete_eq1
    mock_delete_eq1.eq.return_value = mock_delete_eq2
    mock_delete_eq2.execute.return_value = mock_delete_response
    
    # Make the GraphQL request
    response = client.post(
        "/graphql",
        json={
            "query": DELETE_IDEA_MUTATION,
            "variables": {"ideaId": idea_id}
        },
        cookies={"access_token": VALID_TOKEN}
    )
    
    assert response.status_code == 200
    result = response.json()
    assert "errors" not in result
    assert result["data"]["deleteIdea"] is True
    
    # Verify the delete was called
    mock_table.delete.assert_called_once()

def test_delete_idea_not_found(mock_supabase, mock_get_current_user_id):
    """Test deletion of an idea that doesn't exist."""
    idea_id = "non_existent_idea_id"
    
    # Mock the check query to return no data (idea doesn't exist)
    mock_check_response = Mock()
    mock_check_response.data = None
    
    # Setup the mock chain for check
    mock_select = Mock()
    mock_eq1 = Mock()
    mock_eq2 = Mock()
    mock_single = Mock()
    mock_table = mock_supabase.table.return_value
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq1
    mock_eq1.eq.return_value = mock_eq2
    mock_eq2.limit.return_value = mock_single
    mock_single.execute.return_value = mock_check_response
    
    # Make the GraphQL request
    response = client.post(
        "/graphql",
        json={
            "query": DELETE_IDEA_MUTATION,
            "variables": {"ideaId": idea_id}
        },
        cookies={"access_token": VALID_TOKEN}
    )
    
    assert response.status_code == 200
    result = response.json()
    assert "errors" in result
    assert "Idea not found" in result["errors"][0]["message"]
    
    # Verify delete was not called
    mock_table.delete.assert_not_called()

def test_delete_idea_wrong_user(mock_supabase, mock_get_current_user_id):
    """Test deletion of an idea that belongs to a different user."""
    idea_id = "other_user_idea_id"
    
    # Mock the check query to return no data (idea belongs to different user)
    mock_check_response = Mock()
    mock_check_response.data = None
    
    # Setup the mock chain for check
    mock_select = Mock()
    mock_eq1 = Mock()
    mock_eq2 = Mock()
    mock_single = Mock()
    mock_table = mock_supabase.table.return_value
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq1
    mock_eq1.eq.return_value = mock_eq2
    mock_eq2.limit.return_value = mock_single
    mock_single.execute.return_value = mock_check_response
    
    # Make the GraphQL request
    response = client.post(
        "/graphql",
        json={
            "query": DELETE_IDEA_MUTATION,
            "variables": {"ideaId": idea_id}
        },
        cookies={"access_token": VALID_TOKEN}
    )
    
    assert response.status_code == 200
    result = response.json()
    assert "errors" in result
    assert "Idea not found" in result["errors"][0]["message"]
    
    # Verify delete was not called
    mock_table.delete.assert_not_called()

def test_delete_idea_delete_fails(mock_supabase, mock_get_current_user_id):
    """Test deletion when the delete operation fails."""
    idea_id = "test_idea_id"
    
    # Mock the check query to verify idea exists
    mock_check_response = Mock()
    mock_check_response.data = [{"idea_id": idea_id}]
    
    # Mock the delete query to return no data (delete failed)
    mock_delete_response = Mock()
    mock_delete_response.data = None
    
    # Setup the mock chain for check
    mock_select = Mock()
    mock_eq1 = Mock()
    mock_eq2 = Mock()
    mock_single = Mock()
    mock_table = mock_supabase.table.return_value
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq1
    mock_eq1.eq.return_value = mock_eq2
    mock_eq2.limit.return_value = mock_single
    mock_single.execute.return_value = mock_check_response
    
    # Setup the mock chain for delete
    mock_delete = Mock()
    mock_delete_eq1 = Mock()
    mock_delete_eq2 = Mock()
    mock_table.delete.return_value = mock_delete
    mock_delete.eq.return_value = mock_delete_eq1
    mock_delete_eq1.eq.return_value = mock_delete_eq2
    mock_delete_eq2.execute.return_value = mock_delete_response
    
    # Make the GraphQL request
    response = client.post(
        "/graphql",
        json={
            "query": DELETE_IDEA_MUTATION,
            "variables": {"ideaId": idea_id}
        },
        cookies={"access_token": VALID_TOKEN}
    )
    
    assert response.status_code == 200
    result = response.json()
    assert "errors" in result
    assert "Failed to delete idea" in result["errors"][0]["message"]

def test_delete_idea_empty_delete_response(mock_supabase, mock_get_current_user_id):
    """DELETE may return no RETURNING rows (driver/client quirk) while the row
    is actually gone. Resolver re-checks: empty follow-up select => success.
    """
    idea_id = "test_idea_id"

    mock_check_response = Mock()
    mock_check_response.data = [{"idea_id": idea_id}]

    mock_delete_response = Mock()
    mock_delete_response.data = []

    mock_verify_response = Mock()
    mock_verify_response.data = []

    mock_select = Mock()
    mock_eq1 = Mock()
    mock_eq2 = Mock()
    mock_single = Mock()
    mock_table = mock_supabase.table.return_value
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq1
    mock_eq1.eq.return_value = mock_eq2
    mock_eq2.limit.return_value = mock_single
    mock_single.execute.side_effect = [mock_check_response, mock_verify_response]

    mock_delete = Mock()
    mock_delete_eq1 = Mock()
    mock_delete_eq2 = Mock()
    mock_table.delete.return_value = mock_delete
    mock_delete.eq.return_value = mock_delete_eq1
    mock_delete_eq1.eq.return_value = mock_delete_eq2
    mock_delete_eq2.execute.return_value = mock_delete_response

    response = client.post(
        "/graphql",
        json={
            "query": DELETE_IDEA_MUTATION,
            "variables": {"ideaId": idea_id}
        },
        cookies={"access_token": VALID_TOKEN}
    )

    assert response.status_code == 200
    result = response.json()
    assert "errors" not in result
    assert result["data"]["deleteIdea"] is True
    assert mock_single.execute.call_count == 2


def test_delete_idea_empty_returning_but_row_still_present(mock_supabase, mock_get_current_user_id):
    """Empty DELETE payload plus row still visible on verify is a hard failure."""
    idea_id = "test_idea_id"

    mock_check_response = Mock()
    mock_check_response.data = [{"idea_id": idea_id}]

    mock_delete_response = Mock()
    mock_delete_response.data = []

    mock_verify_response = Mock()
    mock_verify_response.data = [{"idea_id": idea_id}]

    mock_select = Mock()
    mock_eq1 = Mock()
    mock_eq2 = Mock()
    mock_single = Mock()
    mock_table = mock_supabase.table.return_value
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq1
    mock_eq1.eq.return_value = mock_eq2
    mock_eq2.limit.return_value = mock_single
    mock_single.execute.side_effect = [mock_check_response, mock_verify_response]

    mock_delete = Mock()
    mock_delete_eq1 = Mock()
    mock_delete_eq2 = Mock()
    mock_table.delete.return_value = mock_delete
    mock_delete.eq.return_value = mock_delete_eq1
    mock_delete_eq1.eq.return_value = mock_delete_eq2
    mock_delete_eq2.execute.return_value = mock_delete_response

    response = client.post(
        "/graphql",
        json={
            "query": DELETE_IDEA_MUTATION,
            "variables": {"ideaId": idea_id}
        },
        cookies={"access_token": VALID_TOKEN}
    )

    assert response.status_code == 200
    result = response.json()
    assert "errors" in result
    assert "Failed to delete idea" in result["errors"][0]["message"]

def test_delete_idea_no_auth_token():
    """Test deletion without authentication token."""
    idea_id = "test_idea_id"
    
    # Make the GraphQL request without auth token
    response = client.post(
        "/graphql",
        json={
            "query": DELETE_IDEA_MUTATION,
            "variables": {"ideaId": idea_id}
        }
    )
    
    # Should fail with 401 or error
    assert response.status_code in [200, 401]
    if response.status_code == 200:
        result = response.json()
        assert "errors" in result


# ---------------------------------------------------------------------------
# Task #48 — regression coverage for production "Failed to delete idea"
# ---------------------------------------------------------------------------
#
# These tests build their own DB stub and inject it via the
# `create_database_client` override the conftest already exposes. That way
# they don't share chained-mock state with the rest of the file (which has
# historically been a source of cross-test pollution) and they can simulate
# the exact psycopg2-style errors the production code path would hit.


def _patch_db_client(monkeypatch, db_stub):
    """Force the GraphQL context's db to be `db_stub` for one test."""
    from app.db import database as _db_module

    monkeypatch.setattr(_db_module, "_db_client_override", db_stub, raising=False)
    monkeypatch.setattr(_db_module, "db_client", db_stub, raising=False)


class _DeleteResolverDbStub:
    """Minimal db client whose `.table("ideas").select(...).eq(...).eq(...).single().execute()`
    chain returns a configurable response, and whose
    `.table("ideas").delete().eq(...).eq(...).execute()` chain optionally
    raises a configurable exception to simulate FK violations.

    We rebuild a fresh chain on every call so two consecutive
    `.table("ideas")` invocations within the same resolver each get clean
    stubs — no cross-method state leak.
    """

    class _Builder:
        def __init__(self, owner: "_DeleteResolverDbStub"):
            self._owner = owner
            self._mode: Optional[str] = None  # "select" or "delete"

        # The query-builder methods just return self, mirroring the real
        # QueryBuilder's fluent interface.
        def select(self, *_args, **_kwargs):
            self._mode = "select"
            return self

        def delete(self):
            self._mode = "delete"
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def single(self):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self._mode == "delete":
                if self._owner.delete_exc is not None:
                    raise self._owner.delete_exc
                return self._owner.delete_response
            # default = select / ownership probe
            return self._owner.check_response

    def __init__(self):
        self.check_response = SimpleNamespace(data=None, error=None)
        self.delete_response = SimpleNamespace(data=[], error=None)
        self.delete_exc: Optional[BaseException] = None
        self.delete_call_count = 0

    def table(self, _name: str):
        return _DeleteResolverDbStub._Builder(self)


def test_delete_idea_translates_foreign_key_violation(
    monkeypatch, mock_get_current_user_id
):
    """A psycopg2 ForeignKeyViolation must surface a friendly, classified
    error instead of being swallowed as a generic "Failed to delete idea".

    This is the failure mode that was hitting production users whose ideas
    had related rows in pitch_decks / product_requirements_documents /
    intellectual_properties / comments before the cascade DDL landed.
    """
    idea_id = "idea_with_children"

    db_stub = _DeleteResolverDbStub()
    db_stub.check_response = SimpleNamespace(data=[{"idea_id": idea_id}], error=None)

    fk_violation = Exception("ForeignKeyViolation: child rows exist")
    fk_violation.pgcode = "23503"  # type: ignore[attr-defined]
    db_stub.delete_exc = fk_violation

    _patch_db_client(monkeypatch, db_stub)

    response = client.post(
        "/graphql",
        json={"query": DELETE_IDEA_MUTATION, "variables": {"ideaId": idea_id}},
        cookies={"access_token": VALID_TOKEN},
    )

    assert response.status_code == 200
    result = response.json()
    assert "errors" in result
    msg = result["errors"][0]["message"]
    # The classified message must mention related records so the operator
    # can reason about it; it must NOT be the bare "Failed to delete idea".
    assert "related records" in msg


def test_delete_idea_classifies_postgrest_code_attribute(
    monkeypatch, mock_get_current_user_id
):
    """Some database clients (PostgREST / supabase-py) raise APIError-style
    objects whose SQLSTATE lives on `.code`, not psycopg2's `.pgcode`.
    The resolver must still classify these as FK violations and produce
    the friendly "related records" message — otherwise users behind those
    clients get the generic "Failed to delete idea" toast.
    """
    idea_id = "idea_with_children_postgrest"

    db_stub = _DeleteResolverDbStub()
    db_stub.check_response = SimpleNamespace(data=[{"idea_id": idea_id}], error=None)

    fk_violation = Exception("APIError: foreign key violation")
    fk_violation.code = "23503"  # type: ignore[attr-defined]
    db_stub.delete_exc = fk_violation

    _patch_db_client(monkeypatch, db_stub)

    response = client.post(
        "/graphql",
        json={"query": DELETE_IDEA_MUTATION, "variables": {"ideaId": idea_id}},
        cookies={"access_token": VALID_TOKEN},
    )

    assert response.status_code == 200
    result = response.json()
    assert "errors" in result
    assert "related records" in result["errors"][0]["message"]


def test_delete_idea_logs_structured_context(
    monkeypatch, mock_get_current_user_id, caplog
):
    """The resolver must emit a structured INFO log with user_id and
    idea_id on the success path so the production "Failed to delete idea"
    incidents can be correlated to actual rows going forward.
    """
    import logging

    idea_id = "logged_idea"

    db_stub = _DeleteResolverDbStub()
    db_stub.check_response = SimpleNamespace(data=[{"idea_id": idea_id}], error=None)
    db_stub.delete_response = SimpleNamespace(data=[{"idea_id": idea_id}], error=None)
    _patch_db_client(monkeypatch, db_stub)

    with caplog.at_level(logging.INFO, logger="manifest"):
        response = client.post(
            "/graphql",
            json={"query": DELETE_IDEA_MUTATION, "variables": {"ideaId": idea_id}},
            cookies={"access_token": VALID_TOKEN},
        )

    assert response.status_code == 200
    assert response.json()["data"]["deleteIdea"] is True

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    # Both start and success markers must include the idea_id so a single
    # request is traceable end-to-end.
    assert "[delete_idea] start" in log_text
    assert "[delete_idea] success" in log_text
    assert idea_id in log_text
