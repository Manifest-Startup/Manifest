import pytest
import os
from unittest.mock import patch, MagicMock
from app.db.database import (
    DatabaseClient,
    InMemoryDatabaseClient,
    QueryBuilder,
    QueryResponse,
    set_db_client_override,
    create_database_client,
    get_database_url,
    get_db_connection,
    get_db_pool_snapshot,
)


class TestGetDatabaseUrl:
    def test_returns_database_url_when_set(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test:test@localhost:5432/testdb"}):
            url = get_database_url()
            assert url == "postgresql://test:test@localhost:5432/testdb"

    def test_returns_none_when_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("app.db.database.logger") as mock_logger:
                url = get_database_url()
                assert url is None
                mock_logger.warning.assert_called()


class TestQueryResponse:
    def test_init_with_data(self):
        response = QueryResponse(data={"id": 1, "name": "test"})
        assert response.data == {"id": 1, "name": "test"}
        assert response.error is None

    def test_init_with_error(self):
        response = QueryResponse(data=None, error="Connection failed")
        assert response.data is None
        assert response.error == "Connection failed"

    def test_init_with_list_data(self):
        data = [{"id": 1}, {"id": 2}]
        response = QueryResponse(data=data)
        assert response.data == data
        assert len(response.data) == 2


class TestQueryBuilder:
    @pytest.fixture
    def client(self):
        return DatabaseClient()

    @pytest.fixture
    def query_builder(self, client):
        return QueryBuilder("users", client)

    def test_select_default(self, query_builder):
        result = query_builder.select()
        assert result._select_cols == "*"
        assert result is query_builder

    def test_select_specific_columns(self, query_builder):
        result = query_builder.select("id, name, email")
        assert result._select_cols == "id, name, email"

    def test_eq_filter(self, query_builder):
        result = query_builder.eq("user_id", "abc123")
        assert '"user_id" = %s' in result._filters
        assert "abc123" in result._filter_values

    def test_neq_filter(self, query_builder):
        result = query_builder.neq("status", "deleted")
        assert '"status" != %s' in result._filters
        assert "deleted" in result._filter_values

    def test_gt_filter(self, query_builder):
        result = query_builder.gt("age", 18)
        assert '"age" > %s' in result._filters
        assert 18 in result._filter_values

    def test_gte_filter(self, query_builder):
        result = query_builder.gte("price", 100)
        assert '"price" >= %s' in result._filters
        assert 100 in result._filter_values

    def test_lt_filter(self, query_builder):
        result = query_builder.lt("quantity", 10)
        assert '"quantity" < %s' in result._filters
        assert 10 in result._filter_values

    def test_lte_filter(self, query_builder):
        result = query_builder.lte("score", 50)
        assert '"score" <= %s' in result._filters
        assert 50 in result._filter_values

    def test_like_filter(self, query_builder):
        result = query_builder.like("name", "%John%")
        assert '"name" LIKE %s' in result._filters
        assert "%John%" in result._filter_values

    def test_ilike_filter(self, query_builder):
        result = query_builder.ilike("email", "%@gmail.com")
        assert '"email" ILIKE %s' in result._filters
        assert "%@gmail.com" in result._filter_values

    def test_is_null_filter(self, query_builder):
        result = query_builder.is_("deleted_at", None)
        assert '"deleted_at" IS NULL' in result._filters

    def test_in_filter(self, query_builder):
        result = query_builder.in_("status", ["active", "pending"])
        assert '"status" IN (%s, %s)' in result._filters
        assert "active" in result._filter_values
        assert "pending" in result._filter_values

    def test_in_empty_list(self, query_builder):
        result = query_builder.in_("status", [])
        assert len(result._filters) == 0

    def test_order_asc(self, query_builder):
        result = query_builder.order("created_at")
        assert result._order_by == "created_at"
        assert result._order_desc is False

    def test_order_desc(self, query_builder):
        result = query_builder.order("created_at", desc=True)
        assert result._order_by == "created_at"
        assert result._order_desc is True

    def test_limit(self, query_builder):
        result = query_builder.limit(10)
        assert result._limit_val == 10

    def test_single(self, query_builder):
        result = query_builder.single()
        assert result._single is True
        assert result._limit_val == 1

    def test_insert(self, query_builder):
        data = {"name": "John", "email": "john@example.com"}
        result = query_builder.insert(data)
        assert result._insert_data == data

    def test_update(self, query_builder):
        data = {"name": "Jane"}
        result = query_builder.update(data)
        assert result._update_data == data

    def test_upsert(self, query_builder):
        data = {"id": 1, "name": "John"}
        result = query_builder.upsert(data, on_conflict="id")
        assert result._upsert_data == data
        assert result._upsert_conflict == "id"

    def test_upsert_with_composite_conflict_string(self, query_builder):
        data = {"follower_id": "user-1", "followed_id": "user-2"}
        result = query_builder.upsert(data, on_conflict="follower_id, followed_id")
        assert result._upsert_conflict == "follower_id, followed_id"

    def test_delete(self, query_builder):
        result = query_builder.delete()
        assert result._delete is True

    def test_method_chaining(self, query_builder):
        result = (
            query_builder
            .select("id, name")
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(5)
        )
        assert result._select_cols == "id, name"
        assert '"status" = %s' in result._filters
        assert result._order_by == "created_at"
        assert result._order_desc is True
        assert result._limit_val == 5


class TestDatabaseClient:
    def test_create_database_client(self):
        set_db_client_override(None)
        with patch.dict(os.environ, {"USE_IN_MEMORY_DB": "1"}, clear=False):
            client = create_database_client()
            assert isinstance(client, InMemoryDatabaseClient)

    def test_table_returns_query_builder(self):
        client = DatabaseClient()
        query = client.table("users")
        assert isinstance(query, QueryBuilder)
        assert query._table == "users"

    def test_multiple_tables(self):
        client = DatabaseClient()
        users = client.table("users")
        ideas = client.table("ideas")
        assert users._table == "users"
        assert ideas._table == "ideas"

    def test_override_client_is_used(self):
        mock_client = MagicMock()
        set_db_client_override(mock_client)
        client = create_database_client()
        assert client is mock_client
        set_db_client_override(None)


class TestInMemoryDatabaseClient:
    def test_insert_and_select(self):
        client = InMemoryDatabaseClient()
        client.table("users").insert({"user_id": "1", "email": "a@example.com"}).execute()
        result = client.table("users").select("*").execute()
        assert result.data == [{"user_id": "1", "email": "a@example.com"}]

    def test_filter_and_update(self):
        client = InMemoryDatabaseClient()
        client.table("ideas").insert({"idea_id": "1", "title": "Old"}).execute()
        client.table("ideas").update({"title": "New"}).eq("idea_id", "1").execute()
        updated = client.table("ideas").select("title").eq("idea_id", "1").single().execute()
        assert updated.data["title"] == "New"

    def test_delete(self):
        client = InMemoryDatabaseClient()
        client.table("ideas").insert({"idea_id": "1"}).execute()
        deleted = client.table("ideas").delete().eq("idea_id", "1").execute()
        assert deleted.data == [{"idea_id": "1"}]
        remaining = client.table("ideas").select("*").execute()
        assert remaining.data == []

    def test_upsert(self):
        client = InMemoryDatabaseClient()
        client.table("ideas").upsert({"idea_id": "1", "title": "First"}, on_conflict=["idea_id"]).execute()
        client.table("ideas").upsert({"idea_id": "1", "title": "Updated"}, on_conflict=["idea_id"]).execute()
        result = client.table("ideas").select("*").execute()
        assert result.data == [{"idea_id": "1", "title": "Updated"}]

    def test_upsert_with_composite_conflict(self):
        client = InMemoryDatabaseClient()
        client.table("user_follows").upsert(
            {"follower_id": "user-1", "followed_id": "user-2", "created_at": "old"},
            on_conflict=["follower_id", "followed_id"],
        ).execute()
        client.table("user_follows").upsert(
            {"follower_id": "user-1", "followed_id": "user-2", "created_at": "new"},
            on_conflict="follower_id, followed_id",
        ).execute()

        result = client.table("user_follows").select("*").execute()
        assert result.data == [{"follower_id": "user-1", "followed_id": "user-2", "created_at": "new"}]


class TestQueryBuilderExecuteSelect:
    @pytest.fixture
    def mock_connection(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor

    def test_execute_select_basic(self, mock_connection):
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "John"},
            {"id": 2, "name": "Jane"}
        ]

        with patch("app.db.database.get_db_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            client = DatabaseClient()
            result = client.table("users").select().execute()

            assert len(result.data) == 2
            assert result.data[0]["name"] == "John"

    def test_execute_select_with_filter(self, mock_connection):
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "John"}]

        with patch("app.db.database.get_db_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            client = DatabaseClient()
            result = client.table("users").select().eq("id", 1).execute()

            mock_cursor.execute.assert_called_once()
            call_args = mock_cursor.execute.call_args
            assert "WHERE" in call_args[0][0]
            assert '"id" = %s' in call_args[0][0]

    def test_execute_single(self, mock_connection):
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "John"}]

        with patch("app.db.database.get_db_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            client = DatabaseClient()
            result = client.table("users").select().eq("id", 1).single().execute()

            assert isinstance(result.data, dict)
            assert result.data["name"] == "John"

    def test_execute_single_empty_result(self, mock_connection):
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = []

        with patch("app.db.database.get_db_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            client = DatabaseClient()
            result = client.table("users").select().eq("id", 999).single().execute()

            assert result.data is None


class TestQueryBuilderExecuteInsert:
    @pytest.fixture
    def mock_connection(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor

    def test_execute_insert(self, mock_connection):
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {"id": 1, "name": "John", "email": "john@example.com"}

        with patch("app.db.database.get_db_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            client = DatabaseClient()
            result = client.table("users").insert({"name": "John", "email": "john@example.com"}).execute()

            assert result.data["name"] == "John"
            call_args = mock_cursor.execute.call_args
            assert "INSERT INTO" in call_args[0][0]
            assert "RETURNING *" in call_args[0][0]


class TestQueryBuilderExecuteUpdate:
    @pytest.fixture
    def mock_connection(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor

    def test_execute_update(self, mock_connection):
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "Jane"}]

        with patch("app.db.database.get_db_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            client = DatabaseClient()
            result = client.table("users").update({"name": "Jane"}).eq("id", 1).execute()

            call_args = mock_cursor.execute.call_args
            assert "UPDATE" in call_args[0][0]
            assert "SET" in call_args[0][0]
            assert "WHERE" in call_args[0][0]


class TestQueryBuilderExecuteUpsert:
    @pytest.fixture
    def mock_connection(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor

    def test_execute_upsert(self, mock_connection):
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {"id": 1, "name": "John"}

        with patch("app.db.database.get_db_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            client = DatabaseClient()
            result = client.table("users").upsert({"id": 1, "name": "John"}, on_conflict="id").execute()

            call_args = mock_cursor.execute.call_args
            assert "INSERT INTO" in call_args[0][0]
            assert "ON CONFLICT" in call_args[0][0]
            assert "DO UPDATE SET" in call_args[0][0]

    def test_execute_upsert_with_composite_conflict(self, mock_connection):
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {"follower_id": "user-1", "followed_id": "user-2"}

        with patch("app.db.database.get_db_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            client = DatabaseClient()
            client.table("user_follows").upsert(
                {"follower_id": "user-1", "followed_id": "user-2"},
                on_conflict="follower_id, followed_id",
            ).execute()

            call_args = mock_cursor.execute.call_args
            assert 'ON CONFLICT ("follower_id", "followed_id")' in call_args[0][0]


class TestQueryBuilderExecuteDelete:
    @pytest.fixture
    def mock_connection(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor

    def test_execute_delete(self, mock_connection):
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "John"}]

        with patch("app.db.database.get_db_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            client = DatabaseClient()
            result = client.table("users").eq("id", 1).delete().execute()

            call_args = mock_cursor.execute.call_args
            assert "DELETE FROM" in call_args[0][0]
            assert "WHERE" in call_args[0][0]
            assert "RETURNING *" in call_args[0][0]


class TestDatabaseClientExecuteRaw:
    @pytest.fixture
    def mock_connection(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = True
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor

    def test_execute_raw_with_results(self, mock_connection):
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [{"count": 10}]

        with patch("app.db.database.get_db_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            client = DatabaseClient()
            result = client.execute_raw("SELECT COUNT(*) as count FROM users")

            assert result.data[0]["count"] == 10

    def test_execute_raw_with_params(self, mock_connection):
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [{"id": 1}]

        with patch("app.db.database.get_db_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            client = DatabaseClient()
            result = client.execute_raw("SELECT * FROM users WHERE id = %s", (1,))

            mock_cursor.execute.assert_called_with("SELECT * FROM users WHERE id = %s", (1,))

    def test_execute_raw_no_results(self, mock_connection):
        mock_conn, mock_cursor = mock_connection
        mock_cursor.description = None

        with patch("app.db.database.get_db_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            client = DatabaseClient()
            result = client.execute_raw("DELETE FROM users WHERE id = %s", (1,))

            assert result.data is None


class TestGetDbPoolSnapshot:
    def test_snapshot_keys_when_no_database_url(self):
        with patch.dict(os.environ, {"DATABASE_URL": "your_database_url_here"}):
            snap = get_db_pool_snapshot()
        assert snap["postgresql_configured"] is False
        assert "min_connections" in snap
        assert "max_connections" in snap
        assert snap["pooled_connections_checked_out"] == 0
