"""Stage #2 — async PostgreSQL pool (psycopg 3.x).

Tests the opt-in async pool without requiring a live Postgres instance.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.db import async_pool


@pytest.fixture(autouse=True)
def _reset_async_pool_state():
    async_pool._async_pool = None
    async_pool._async_pool_open = False
    yield
    async_pool._async_pool = None
    async_pool._async_pool_open = False


def test_async_db_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ASYNC_DB", raising=False)
    assert async_pool.async_db_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
def test_async_db_enabled_values(monkeypatch, value):
    monkeypatch.setenv("ASYNC_DB", value)
    assert async_pool.async_db_enabled() is True


@pytest.mark.asyncio
async def test_init_async_pool_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("ASYNC_DB", raising=False)
    await async_pool.init_async_pool()
    assert async_pool._async_pool is None
    assert async_pool._async_pool_open is False


@pytest.mark.asyncio
async def test_init_async_pool_skips_without_database_url(monkeypatch):
    monkeypatch.setenv("ASYNC_DB", "true")
    monkeypatch.setattr(async_pool, "get_database_url", lambda: None)
    await async_pool.init_async_pool()
    assert async_pool._async_pool is None


@pytest.mark.asyncio
async def test_get_async_connection_raises_when_pool_not_open():
    with pytest.raises(RuntimeError, match="Async DB pool is not open"):
        async with async_pool.get_async_connection():
            pass


@pytest.mark.asyncio
async def test_ping_async_db_false_when_disabled(monkeypatch):
    monkeypatch.delenv("ASYNC_DB", raising=False)
    assert await async_pool.ping_async_db() is False


def test_get_async_pool_snapshot_reports_disabled(monkeypatch):
    monkeypatch.delenv("ASYNC_DB", raising=False)
    snapshot = async_pool.get_async_pool_snapshot()
    assert snapshot["async_db_enabled"] is False
    assert snapshot["pool_open"] is False


def test_get_async_pool_snapshot_reports_enabled_without_open_pool(monkeypatch):
    monkeypatch.setenv("ASYNC_DB", "true")
    snapshot = async_pool.get_async_pool_snapshot()
    assert snapshot["async_db_enabled"] is True
    assert snapshot["pool_open"] is False
