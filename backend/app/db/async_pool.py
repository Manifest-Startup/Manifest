"""Async PostgreSQL connection pool — Stage #2 of the backend migration.

Adds a ``psycopg`` 3.x ``AsyncConnectionPool`` alongside the existing
sync ``psycopg2`` ``ThreadedConnectionPool``. Both paths coexist:

* **Default (``ASYNC_DB`` unset / false):** unchanged sync ``QueryBuilder``
  via ``psycopg2`` — zero behaviour change for existing resolvers.
* **Opt-in (``ASYNC_DB=true``):** async pool opens at FastAPI startup;
  async resolvers and health checks can ``await get_async_connection()``
  without blocking the event loop on socket I/O.

Why not replace psycopg2 yet
----------------------------
441 Python files call the sync ``DatabaseClient.table(...).execute()``
API. Migrating them all in one PR is high risk. Stage #2 ships the pool
and ``execute_raw_async`` so Stage #3+ can opt hot paths in one resolver
at a time behind the same ``ASYNC_DB`` flag.

Env vars
--------
* ``ASYNC_DB`` — ``true`` / ``1`` / ``yes`` to enable (default off).
* ``ASYNC_DB_POOL_MIN`` — min pool size (falls back to ``DB_POOL_MIN_CONNECTIONS``).
* ``ASYNC_DB_POOL_MAX`` — max pool size (falls back to ``DB_POOL_MAX_CONNECTIONS``).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from app.db.database import _record_connection_opened, get_database_url
from app.utils.logger import logger

try:
    from psycopg import AsyncConnection
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool
except ModuleNotFoundError:
    AsyncConnection = None  # type: ignore[misc, assignment]
    AsyncConnectionPool = None  # type: ignore[misc, assignment]
    dict_row = None  # type: ignore[misc, assignment]

_async_pool: AsyncConnectionPool | None = None
_async_pool_open = False


def async_db_enabled() -> bool:
    """Return True when the async pool should be initialized at startup."""
    return os.getenv("ASYNC_DB", "").strip().lower() in {"1", "true", "yes", "on"}


def async_pool_available() -> bool:
    """True when psycopg3 + pool deps are importable."""
    return AsyncConnectionPool is not None


def get_async_pool_snapshot() -> dict[str, Any]:
    """Non-sensitive async pool stats for ``GET /api/internal/ops/snapshot``."""
    enabled = async_db_enabled()
    url = get_database_url()
    min_size = max(
        1, int(os.getenv("ASYNC_DB_POOL_MIN", os.getenv("DB_POOL_MIN_CONNECTIONS", "1")))
    )
    max_size = max(
        min_size, int(os.getenv("ASYNC_DB_POOL_MAX", os.getenv("DB_POOL_MAX_CONNECTIONS", "10")))
    )

    snapshot: dict[str, Any] = {
        "async_db_enabled": enabled,
        "driver_available": async_pool_available(),
        "postgresql_configured": bool(url),
        "pool_open": _async_pool_open and _async_pool is not None,
        "min_connections": min_size,
        "max_connections": max_size,
    }

    if _async_pool is not None and _async_pool_open:
        try:
            stats = _async_pool.get_stats()
            snapshot["connections_in_pool"] = stats.get("pool_size", 0)
            snapshot["connections_available"] = stats.get("pool_available", 0)
            snapshot["requests_waiting"] = stats.get("requests_waiting", 0)
        except Exception as exc:  # noqa: BLE001 — ops snapshot must not fail
            snapshot["stats_error"] = str(exc)

    return snapshot


async def init_async_pool() -> None:
    """Open the async pool during FastAPI startup (no-op when disabled)."""
    global _async_pool, _async_pool_open

    if not async_db_enabled():
        logger.info("[async_db] ASYNC_DB not enabled; sync psycopg2 path only")
        return

    if not async_pool_available():
        logger.warning(
            "[async_db] ASYNC_DB=true but psycopg[binary,pool] is not installed; "
            "install backend requirements to enable the async pool"
        )
        return

    database_url = get_database_url()
    if not database_url:
        logger.warning(
            "[async_db] ASYNC_DB=true but DATABASE_URL is not configured; "
            "async pool skipped (in-memory mode uses sync client only)"
        )
        return

    if _async_pool_open and _async_pool is not None:
        return

    min_size = max(
        1, int(os.getenv("ASYNC_DB_POOL_MIN", os.getenv("DB_POOL_MIN_CONNECTIONS", "1")))
    )
    max_size = max(
        min_size, int(os.getenv("ASYNC_DB_POOL_MAX", os.getenv("DB_POOL_MAX_CONNECTIONS", "10")))
    )

    _async_pool = AsyncConnectionPool(
        conninfo=database_url,
        min_size=min_size,
        max_size=max_size,
        kwargs={"row_factory": dict_row},
        open=False,
    )
    await _async_pool.open()
    _async_pool_open = True
    logger.info(
        "[async_db] AsyncConnectionPool opened (min=%s, max=%s)",
        min_size,
        max_size,
    )


async def close_async_pool() -> None:
    """Close the async pool during FastAPI shutdown."""
    global _async_pool, _async_pool_open

    if _async_pool is None:
        return

    try:
        await _async_pool.close()
    finally:
        _async_pool = None
        _async_pool_open = False
        logger.info("[async_db] AsyncConnectionPool closed")


@asynccontextmanager
async def get_async_connection():
    """Yield an async connection from the pool (commits on clean exit).

    Raises ``RuntimeError`` if the pool was not initialized — callers should
    check ``async_db_enabled()`` and ``get_async_pool_snapshot()["pool_open"]``
    before relying on this in production paths.
    """
    if _async_pool is None or not _async_pool_open:
        raise RuntimeError(
            "Async DB pool is not open. Set ASYNC_DB=true and ensure "
            "DATABASE_URL is configured before calling get_async_connection()."
        )

    async with _async_pool.connection() as conn:
        _record_connection_opened()
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


async def execute_raw_async(sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    """Run a parameterized SQL statement on the async pool.

    Returns fetched rows as dicts when the statement produces a result set,
    otherwise an empty list. Intended as the low-level building block for
    resolver-level migration in Stages #3+.
    """
    import time

    from app.db.database import _record_query

    started_at = time.perf_counter()
    try:
        async with get_async_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(sql, params or ())
                if cursor.description:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
                return []
    finally:
        _record_query("raw", "raw_async", (time.perf_counter() - started_at) * 1000)


async def ping_async_db() -> bool:
    """Return True when ``SELECT 1`` succeeds on the async pool."""
    if not async_db_enabled() or not _async_pool_open:
        return False
    try:
        rows = await execute_raw_async("SELECT 1 AS ok")
        return bool(rows) and rows[0].get("ok") == 1
    except Exception as exc:  # noqa: BLE001 — health check must not raise
        logger.warning("[async_db] ping failed: %s", exc)
        return False
