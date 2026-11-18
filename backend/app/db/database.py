import copy
import os
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from app.security.config import configured_database_url
from app.utils.logger import logger

try:
    import psycopg2  # type: ignore
    from psycopg2.extras import RealDictCursor  # type: ignore
    from psycopg2.pool import ThreadedConnectionPool  # type: ignore
except ModuleNotFoundError:
    # Keep module importable in environments where psycopg2 is unavailable
    # (e.g. offline CI / sandbox). Real DB connections still fail explicitly.
    class _Psycopg2Stub:
        class Error(Exception):
            pass

        class OperationalError(Error):
            pass

        class InterfaceError(Error):
            pass

        @staticmethod
        def connect(*args, **kwargs):
            raise RuntimeError(
                "psycopg2 is not installed. Install psycopg2-binary to use "
                "PostgreSQL connections, or set USE_IN_MEMORY_DB=1."
            )

    psycopg2 = _Psycopg2Stub()  # type: ignore
    ThreadedConnectionPool = None  # type: ignore

    class RealDictCursor:  # type: ignore
        pass


_query_metrics: ContextVar[dict[str, Any] | None] = ContextVar("query_metrics", default=None)
_SLOW_QUERY_THRESHOLD_MS = float(os.getenv("DB_SLOW_QUERY_THRESHOLD_MS", "100"))
_db_pool = None
_pool_in_use_lock = threading.Lock()
_pool_connections_checked_out: int = 0


def _increment_pooled_connection_in_use() -> None:
    global _pool_connections_checked_out
    with _pool_in_use_lock:
        _pool_connections_checked_out += 1


def _decrement_pooled_connection_in_use() -> None:
    global _pool_connections_checked_out
    with _pool_in_use_lock:
        if _pool_connections_checked_out > 0:
            _pool_connections_checked_out -= 1


def get_db_pool_snapshot() -> dict[str, Any]:
    """Lightweight pool stats for ops dashboards (see docs/OBSERVABILITY_AND_SLO.md)."""
    url_configured = bool(configured_database_url())
    pooling = _pooling_enabled() and ThreadedConnectionPool is not None and url_configured
    min_c = max(1, int(os.getenv("DB_POOL_MIN_CONNECTIONS", "1")))
    max_c = max(min_c, int(os.getenv("DB_POOL_MAX_CONNECTIONS", "10")))
    with _pool_in_use_lock:
        checked_out = _pool_connections_checked_out
    return {
        "postgresql_configured": url_configured,
        "pooling_enabled": pooling,
        "pool_initialized": _db_pool is not None,
        "min_connections": min_c,
        "max_connections": max_c,
        "pooled_connections_checked_out": checked_out,
    }


def begin_query_metrics():
    """Start collecting DB work for the current request/task."""
    return _query_metrics.set(
        {
            "query_count": 0,
            "connection_count": 0,
            "total_query_ms": 0.0,
            "slow_queries": [],
        }
    )


def end_query_metrics(token) -> dict[str, Any]:
    metrics = _query_metrics.get() or {}
    _query_metrics.reset(token)
    return metrics


def _record_connection_opened() -> None:
    metrics = _query_metrics.get()
    if metrics is not None:
        metrics["connection_count"] = int(metrics.get("connection_count", 0)) + 1


def _record_query(table: str, operation: str, duration_ms: float) -> None:
    metrics = _query_metrics.get()
    if metrics is None:
        return

    metrics["query_count"] = int(metrics.get("query_count", 0)) + 1
    metrics["total_query_ms"] = float(metrics.get("total_query_ms", 0.0)) + duration_ms
    if duration_ms >= _SLOW_QUERY_THRESHOLD_MS:
        metrics.setdefault("slow_queries", []).append(
            {
                "table": table,
                "operation": operation,
                "duration_ms": round(duration_ms, 2),
            }
        )


def _pooling_enabled() -> bool:
    return os.getenv("DB_POOL_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def _get_pooled_connection(database_url: str):
    global _db_pool
    if not _pooling_enabled() or ThreadedConnectionPool is None:
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor), False

    if _db_pool is None:
        minconn = max(1, int(os.getenv("DB_POOL_MIN_CONNECTIONS", "1")))
        maxconn = max(minconn, int(os.getenv("DB_POOL_MAX_CONNECTIONS", "10")))
        _db_pool = ThreadedConnectionPool(
            minconn,
            maxconn,
            database_url,
            cursor_factory=RealDictCursor,
        )
        logger.info(f"Initialized PostgreSQL connection pool ({minconn}-{maxconn})")

    return _db_pool.getconn(), True


_database_url_logged = False


def get_database_url():
    """Get DATABASE_URL for database connections.

    Production uses the Supabase Postgres session pooler; without a URL the app
    falls back to the in-memory demo database.
    """
    global _database_url_logged
    raw_in_env = (os.getenv("DATABASE_URL") or "").strip()
    url = configured_database_url()

    if url:
        # Called on every connection checkout; log once, not per query.
        if not _database_url_logged:
            logger.info("Using PostgreSQL database from DATABASE_URL")
            _database_url_logged = True
    elif raw_in_env:
        logger.warning(
            "DATABASE_URL is set to a template or invalid value; using in-memory DB / demo. "
            "Set a real Postgres connection string in .env to use PostgreSQL."
        )
    else:
        logger.warning("DATABASE_URL is not set. Using in-memory DB when supported.")

    return url


@contextmanager
def get_db_connection():
    conn = None
    from_pool = False
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    try:
        conn, from_pool = _get_pooled_connection(database_url)
        if from_pool:
            _increment_pooled_connection_in_use()
        _record_connection_opened()
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            if from_pool and _db_pool is not None:
                try:
                    _db_pool.putconn(conn)
                finally:
                    _decrement_pooled_connection_in_use()
            else:
                conn.close()


def _adapt_value(value: Any) -> Any:
    """psycopg2 sends lists as arrays but cannot send dicts; send dicts as JSON (jsonb columns)."""
    if isinstance(value, dict):
        from psycopg2.extras import Json

        return Json(value)
    return value


class QueryBuilder:
    def __init__(self, table_name: str, client: "DatabaseClient"):
        self._table = table_name
        self._client = client
        self._select_cols = "*"
        self._filters = []
        self._filter_values = []
        self._order_by = None
        self._order_desc = False
        self._limit_val = None
        self._offset_val = None
        self._single = False
        self._insert_data = None
        self._update_data = None
        self._upsert_data = None
        self._upsert_conflict = None
        self._delete = False

    @staticmethod
    def _normalize_conflict_columns(conflict: Any) -> list[str]:
        if conflict is None:
            return []

        raw_columns = conflict if isinstance(conflict, list | tuple) else str(conflict).split(",")

        return [str(column).strip().strip('"') for column in raw_columns if str(column).strip()]

    def select(self, columns: str = "*") -> "QueryBuilder":
        self._select_cols = columns
        return self

    def eq(self, column: str, value: Any) -> "QueryBuilder":
        self._filters.append(f'"{column}" = %s')
        self._filter_values.append(value)
        return self

    def neq(self, column: str, value: Any) -> "QueryBuilder":
        self._filters.append(f'"{column}" != %s')
        self._filter_values.append(value)
        return self

    def or_(self, expression: str) -> "QueryBuilder":
        clauses = []
        values = []
        for condition in expression.split(","):
            parts = condition.split(".", 2)
            if len(parts) != 3:
                continue
            column, operator, value = parts
            if operator == "eq":
                clauses.append(f'"{column}" = %s')
                values.append(value)
        if clauses:
            self._filters.append("(" + " OR ".join(clauses) + ")")
            self._filter_values.extend(values)
        return self

    def gt(self, column: str, value: Any) -> "QueryBuilder":
        self._filters.append(f'"{column}" > %s')
        self._filter_values.append(value)
        return self

    def gte(self, column: str, value: Any) -> "QueryBuilder":
        self._filters.append(f'"{column}" >= %s')
        self._filter_values.append(value)
        return self

    def lt(self, column: str, value: Any) -> "QueryBuilder":
        self._filters.append(f'"{column}" < %s')
        self._filter_values.append(value)
        return self

    def lte(self, column: str, value: Any) -> "QueryBuilder":
        self._filters.append(f'"{column}" <= %s')
        self._filter_values.append(value)
        return self

    def like(self, column: str, pattern: str) -> "QueryBuilder":
        self._filters.append(f'"{column}" LIKE %s')
        self._filter_values.append(pattern)
        return self

    def ilike(self, column: str, pattern: str) -> "QueryBuilder":
        self._filters.append(f'"{column}" ILIKE %s')
        self._filter_values.append(pattern)
        return self

    def is_(self, column: str, value: Any) -> "QueryBuilder":
        if value is None:
            self._filters.append(f'"{column}" IS NULL')
        else:
            self._filters.append(f'"{column}" IS %s')
            self._filter_values.append(value)
        return self

    def in_(self, column: str, values: list[Any]) -> "QueryBuilder":
        if values:
            placeholders = ", ".join(["%s"] * len(values))
            self._filters.append(f'"{column}" IN ({placeholders})')
            self._filter_values.extend(values)
        return self

    def order(self, column: str, desc: bool = False) -> "QueryBuilder":
        self._order_by = column
        self._order_desc = desc
        return self

    def limit(self, count: int) -> "QueryBuilder":
        self._limit_val = count
        return self

    def range(self, start: int, end: int) -> "QueryBuilder":
        self._offset_val = max(0, start)
        self._limit_val = max(0, end - start + 1)
        return self

    def single(self) -> "QueryBuilder":
        self._single = True
        self._limit_val = 1
        return self

    def insert(self, data: dict[str, Any]) -> "QueryBuilder":
        self._insert_data = data
        return self

    def update(self, data: dict[str, Any]) -> "QueryBuilder":
        self._update_data = data
        return self

    def upsert(self, data: dict[str, Any], on_conflict: str = None) -> "QueryBuilder":
        self._upsert_data = data
        self._upsert_conflict = on_conflict
        return self

    def delete(self) -> "QueryBuilder":
        self._delete = True
        return self

    def execute(self) -> "QueryResponse":
        operation = self._operation_name()
        started_at = time.perf_counter()
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                if self._insert_data:
                    return self._execute_insert(cursor)
                elif self._update_data:
                    return self._execute_update(cursor)
                elif self._upsert_data:
                    return self._execute_upsert(cursor)
                elif self._delete:
                    return self._execute_delete(cursor)
                else:
                    return self._execute_select(cursor)
        finally:
            _record_query(self._table, operation, (time.perf_counter() - started_at) * 1000)

    def _operation_name(self) -> str:
        if self._insert_data:
            return "insert"
        if self._update_data:
            return "update"
        if self._upsert_data:
            return "upsert"
        if self._delete:
            return "delete"
        return "select"

    def _execute_select(self, cursor) -> "QueryResponse":
        sql = f'SELECT {self._select_cols} FROM "{self._table}"'

        if self._filters:
            sql += " WHERE " + " AND ".join(self._filters)

        if self._order_by:
            sql += f' ORDER BY "{self._order_by}"'
            if self._order_desc:
                sql += " DESC"

        if self._limit_val:
            sql += f" LIMIT {self._limit_val}"

        if self._offset_val:
            sql += f" OFFSET {self._offset_val}"

        cursor.execute(sql, self._filter_values)
        rows = cursor.fetchall()

        data = (dict(rows[0]) if rows else None) if self._single else [dict(row) for row in rows]

        return QueryResponse(data=data, error=None)

    def _execute_insert(self, cursor) -> "QueryResponse":
        columns = list(self._insert_data.keys())
        values = [_adapt_value(v) for v in self._insert_data.values()]
        col_str = ", ".join(f'"{c}"' for c in columns)
        placeholders = ", ".join(["%s"] * len(values))

        sql = f'INSERT INTO "{self._table}" ({col_str}) VALUES ({placeholders}) RETURNING *'
        cursor.execute(sql, values)
        row = cursor.fetchone()

        return QueryResponse(data=dict(row) if row else None, error=None)

    def _execute_update(self, cursor) -> "QueryResponse":
        set_clauses = []
        update_values = []
        for col, val in self._update_data.items():
            set_clauses.append(f'"{col}" = %s')
            update_values.append(_adapt_value(val))

        sql = f'UPDATE "{self._table}" SET {", ".join(set_clauses)}'

        if self._filters:
            sql += " WHERE " + " AND ".join(self._filters)

        sql += " RETURNING *"

        all_values = update_values + self._filter_values
        cursor.execute(sql, all_values)
        rows = cursor.fetchall()

        data = (dict(rows[0]) if rows else None) if self._single else [dict(row) for row in rows]

        return QueryResponse(data=data, error=None)

    def _execute_upsert(self, cursor) -> "QueryResponse":
        columns = list(self._upsert_data.keys())
        values = [_adapt_value(v) for v in self._upsert_data.values()]
        col_str = ", ".join(f'"{c}"' for c in columns)
        placeholders = ", ".join(["%s"] * len(values))

        update_clauses = [f'"{c}" = EXCLUDED."{c}"' for c in columns]
        conflict_columns = self._normalize_conflict_columns(self._upsert_conflict) or [columns[0]]
        conflict_sql = ", ".join(f'"{column}"' for column in conflict_columns)

        sql = f"""
            INSERT INTO "{self._table}" ({col_str}) 
            VALUES ({placeholders}) 
            ON CONFLICT ({conflict_sql}) 
            DO UPDATE SET {", ".join(update_clauses)}
            RETURNING *
        """
        cursor.execute(sql, values)
        row = cursor.fetchone()

        return QueryResponse(data=dict(row) if row else None, error=None)

    def _execute_delete(self, cursor) -> "QueryResponse":
        sql = f'DELETE FROM "{self._table}"'

        if self._filters:
            sql += " WHERE " + " AND ".join(self._filters)

        sql += " RETURNING *"
        cursor.execute(sql, self._filter_values)
        rows = cursor.fetchall()

        return QueryResponse(data=[dict(row) for row in rows], error=None)


class QueryResponse:
    def __init__(self, data: Any, error: str | None = None):
        self.data = data
        self.error = error


class DatabaseClient:
    def __init__(self):
        pass

    def table(self, name: str) -> QueryBuilder:
        return QueryBuilder(name, self)

    def execute_raw(self, sql: str, params: tuple = None) -> QueryResponse:
        started_at = time.perf_counter()
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params or ())
                if cursor.description:
                    rows = cursor.fetchall()
                    return QueryResponse(data=[dict(row) for row in rows], error=None)
                return QueryResponse(data=None, error=None)
        finally:
            _record_query("raw", "raw", (time.perf_counter() - started_at) * 1000)


def create_database_client() -> DatabaseClient:
    if _db_client_override is not None:
        return _db_client_override

    url = get_database_url()
    use_memory = os.getenv("USE_IN_MEMORY_DB", "").lower() in ("1", "true", "yes") or not url

    if use_memory:
        logger.warning(
            "Using in-memory database client (DATABASE_URL not configured). Data will not persist across restarts."
        )
        return _get_in_memory_client()

    return DatabaseClient()


class InMemoryQuery:
    """Lightweight in-memory query builder used when DATABASE_URL is unavailable.

    Supports the minimal subset of query behaviors required by the app and tests:
    select/insert/update/delete/upsert with filter chaining and optional ordering/limits.
    """

    def __init__(self, table_name: str, store: dict[str, list]):
        self._table = table_name
        self._store = store
        self._filters: list[Callable[[dict[str, Any]], bool]] = []
        self._select_cols = "*"
        self._order_by: str | None = None
        self._order_desc = False
        self._limit_val: int | None = None
        self._offset_val: int | None = None
        self._single = False
        self._insert_data: dict[str, Any] | None = None
        self._update_data: dict[str, Any] | None = None
        self._upsert_data: dict[str, Any] | None = None
        self._upsert_conflict: str | list[str] | None = None
        self._delete = False

    @staticmethod
    def _normalize_conflict_columns(conflict: Any) -> list[str]:
        if conflict is None:
            return []

        raw_columns = conflict if isinstance(conflict, list | tuple) else str(conflict).split(",")

        return [str(column).strip().strip('"') for column in raw_columns if str(column).strip()]

    # Filter + projection helpers
    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = rows
        for predicate in self._filters:
            result = [row for row in result if predicate(row)]
        return result

    def _apply_select(self, row: dict[str, Any]) -> dict[str, Any]:
        if self._select_cols == "*" or not self._select_cols:
            return copy.deepcopy(row)
        columns = [col.strip().strip('"') for col in self._select_cols.split(",")]
        return {col: row.get(col) for col in columns}

    def _apply_order(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self._order_by:
            return rows
        return sorted(rows, key=lambda r: r.get(self._order_by), reverse=self._order_desc)

    # Query API (mirrors QueryBuilder)
    def select(self, columns: str = "*") -> "InMemoryQuery":
        self._select_cols = columns
        return self

    def eq(self, column: str, value: Any) -> "InMemoryQuery":
        self._filters.append(lambda row: row.get(column) == value)
        return self

    def neq(self, column: str, value: Any) -> "InMemoryQuery":
        self._filters.append(lambda row: row.get(column) != value)
        return self

    def or_(self, expression: str) -> "InMemoryQuery":
        conditions: list[tuple[str, str, str]] = []
        for condition in expression.split(","):
            parts = condition.split(".", 2)
            if len(parts) == 3:
                conditions.append((parts[0], parts[1], parts[2]))

        if conditions:
            self._filters.append(
                lambda row: any(
                    operator == "eq" and str(row.get(column)) == value
                    for column, operator, value in conditions
                )
            )
        return self

    def gt(self, column: str, value: Any) -> "InMemoryQuery":
        self._filters.append(lambda row: row.get(column) is not None and row.get(column) > value)
        return self

    def gte(self, column: str, value: Any) -> "InMemoryQuery":
        self._filters.append(lambda row: row.get(column) is not None and row.get(column) >= value)
        return self

    def lt(self, column: str, value: Any) -> "InMemoryQuery":
        self._filters.append(lambda row: row.get(column) is not None and row.get(column) < value)
        return self

    def lte(self, column: str, value: Any) -> "InMemoryQuery":
        self._filters.append(lambda row: row.get(column) is not None and row.get(column) <= value)
        return self

    def like(self, column: str, pattern: str) -> "InMemoryQuery":
        from fnmatch import fnmatch

        self._filters.append(
            lambda row: fnmatch(str(row.get(column, "")), pattern.replace("%", "*"))
        )
        return self

    def ilike(self, column: str, pattern: str) -> "InMemoryQuery":
        lower_pattern = pattern.lower()
        self._filters.append(
            lambda row: lower_pattern.replace("%", "") in str(row.get(column, "")).lower()
        )
        return self

    def is_(self, column: str, value: Any) -> "InMemoryQuery":
        if value is None:
            self._filters.append(lambda row: row.get(column) is None)
        else:
            self._filters.append(lambda row: row.get(column) is value)
        return self

    def in_(self, column: str, values: list[Any]) -> "InMemoryQuery":
        if values:
            lookup = set(values)
            self._filters.append(lambda row: row.get(column) in lookup)
        return self

    def order(self, column: str, desc: bool = False) -> "InMemoryQuery":
        self._order_by = column
        self._order_desc = desc
        return self

    def limit(self, count: int) -> "InMemoryQuery":
        self._limit_val = count
        return self

    def range(self, start: int, end: int) -> "InMemoryQuery":
        self._offset_val = max(0, start)
        self._limit_val = max(0, end - start + 1)
        return self

    def single(self) -> "InMemoryQuery":
        self._single = True
        self._limit_val = 1
        return self

    def insert(self, data: dict[str, Any]) -> "InMemoryQuery":
        self._insert_data = data
        return self

    def update(self, data: dict[str, Any]) -> "InMemoryQuery":
        self._update_data = data
        return self

    def upsert(self, data: dict[str, Any], on_conflict: str = None) -> "InMemoryQuery":
        self._upsert_data = data
        self._upsert_conflict = on_conflict
        return self

    def delete(self) -> "InMemoryQuery":
        self._delete = True
        return self

    # Execution
    def execute(self) -> QueryResponse:
        operation = self._operation_name()
        started_at = time.perf_counter()
        try:
            table_rows = self._store[self._table]

            if self._insert_data is not None:
                row = copy.deepcopy(self._insert_data)
                table_rows.append(row)
                return QueryResponse(data=row, error=None)

            if self._update_data is not None:
                matched_rows = self._apply_filters(table_rows)
                updated_rows = []
                for row in matched_rows:
                    row.update(self._update_data)
                    updated_rows.append(copy.deepcopy(row))
                data = updated_rows[0] if self._single and updated_rows else updated_rows
                return QueryResponse(data=data, error=None)

            if self._upsert_data is not None:
                conflict_columns = self._normalize_conflict_columns(self._upsert_conflict)

                if conflict_columns:
                    existing_row = next(
                        (
                            row
                            for row in table_rows
                            if all(
                                row.get(column) == self._upsert_data.get(column)
                                for column in conflict_columns
                            )
                        ),
                        None,
                    )
                else:
                    existing_row = None

                if existing_row is not None:
                    existing_row.update(self._upsert_data)
                    return QueryResponse(data=copy.deepcopy(existing_row), error=None)

                row = copy.deepcopy(self._upsert_data)
                table_rows.append(row)
                return QueryResponse(data=row, error=None)

            if self._delete:
                remaining_rows = []
                deleted_rows = []
                for row in table_rows:
                    if all(pred(row) for pred in self._filters):
                        deleted_rows.append(copy.deepcopy(row))
                    else:
                        remaining_rows.append(row)
                self._store[self._table] = remaining_rows
                return QueryResponse(data=deleted_rows, error=None)

            # Default: SELECT path
            rows = self._apply_filters(table_rows)
            rows = [self._apply_select(row) for row in rows]
            rows = self._apply_order(rows)
            if self._offset_val is not None:
                rows = rows[self._offset_val :]
            if self._limit_val is not None:
                rows = rows[: self._limit_val]
            data = (rows[0] if rows else None) if self._single else rows
            return QueryResponse(data=data, error=None)
        finally:
            _record_query(self._table, operation, (time.perf_counter() - started_at) * 1000)

    def _operation_name(self) -> str:
        if self._insert_data is not None:
            return "insert"
        if self._update_data is not None:
            return "update"
        if self._upsert_data is not None:
            return "upsert"
        if self._delete:
            return "delete"
        return "select"


class InMemoryDatabaseClient:
    def __init__(self, store: dict[str, list] | None = None):
        self._store = store or defaultdict(list)

    def table(self, name: str) -> InMemoryQuery:
        return InMemoryQuery(name, self._store)

    def execute_raw(self, sql: str, params: tuple = None) -> QueryResponse:
        logger.warning("execute_raw is not supported in in-memory mode.")
        return QueryResponse(data=None, error="execute_raw not supported in memory mode")

    def reset(self):
        """Testing helper to clear all in-memory tables."""
        self._store.clear()


_in_memory_store: dict[str, list] = defaultdict(list)
_in_memory_client: InMemoryDatabaseClient | None = None
_db_client_override: Any | None = None


def _get_in_memory_client() -> InMemoryDatabaseClient:
    global _in_memory_client
    if _in_memory_client is None:
        _in_memory_client = InMemoryDatabaseClient(_in_memory_store)
    return _in_memory_client


def set_db_client_override(client: Any):
    """Allow tests to supply a mock client that will be reused by create_database_client."""
    global _db_client_override, db_client
    _db_client_override = client
    db_client = create_database_client() if client is None else client


db_client = create_database_client()
