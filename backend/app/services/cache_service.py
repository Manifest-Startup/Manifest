"""Process-wide cache with a Redis backend when ``REDIS_URL`` is set, and a
safe in-process TTL fallback otherwise.

Phase 4 of the Performance Migration Strategy. Routing a hot read or the AI
response cache through here makes it **shared across workers and instances**
once Redis is provisioned, with **zero behaviour change until then** — when
``REDIS_URL`` is unset (or Redis is unreachable) it behaves exactly like the
in-process dict it replaces.

Fail-safe by construction: every Redis error degrades to a cache-miss / no-op,
so the cache can never break a request. Values are JSON-serialized, so only
JSON-compatible values (str / dict / list / number / bool / None) are cached;
anything else is silently skipped.

Env:
  REDIS_URL  — e.g. ``redis://default:pass@host:6379/0``. Unset → in-process.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from app.utils.logger import logger

_lock = threading.Lock()
_local: dict[str, tuple[float, Any]] = {}

_redis_client: Any = None
_redis_init_attempted = False


def _redis_url() -> str:
    return os.getenv("REDIS_URL", "").strip()


def _get_redis() -> Any:
    """Lazily build a Redis client, once. Returns None if Redis is not
    configured or not reachable (so callers fall back to the in-process map)."""
    global _redis_client, _redis_init_attempted
    if not _redis_url():
        return None
    if _redis_init_attempted:
        return _redis_client
    _redis_init_attempted = True
    try:
        import redis  # imported lazily so the dep is optional until used

        client = redis.Redis.from_url(
            _redis_url(),
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
            decode_responses=True,
        )
        client.ping()
        _redis_client = client
        logger.info("[cache] Redis backend enabled")
    except Exception as exc:  # pragma: no cover - depends on env
        logger.warning(
            "[cache] REDIS_URL set but Redis unavailable (%s); using in-process cache", exc
        )
        _redis_client = None
    return _redis_client


def cache_backend() -> str:
    """``"redis"`` if a live Redis client is in use, else ``"memory"``."""
    return "redis" if _get_redis() is not None else "memory"


def cache_get(key: str) -> Any:
    """Return the cached value for ``key`` or None (miss / expired / error)."""
    client = _get_redis()
    if client is not None:
        try:
            raw = client.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception as exc:  # pragma: no cover - depends on env
            logger.debug("[cache] redis get failed (%s); treating as miss", exc)
            return None

    now = time.time()
    with _lock:
        cached = _local.get(key)
        if not cached:
            return None
        expires_at, value = cached
        if expires_at <= now:
            _local.pop(key, None)
            return None
        return value


def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    """Cache ``value`` under ``key`` for ``ttl_seconds``. No-op on any error."""
    ttl = max(1, int(ttl_seconds))
    client = _get_redis()
    if client is not None:
        try:
            client.set(key, json.dumps(value), ex=ttl)
        except Exception as exc:  # pragma: no cover - depends on env
            logger.debug("[cache] redis set failed (%s); skipping", exc)
        return

    with _lock:
        _local[key] = (time.time() + ttl, value)


def cache_delete(key: str) -> None:
    """Invalidate ``key`` (used by mutations to drop a stale read)."""
    client = _get_redis()
    if client is not None:
        try:
            client.delete(key)
        except Exception:  # pragma: no cover - depends on env
            pass
        return
    with _lock:
        _local.pop(key, None)


def _reset_for_tests() -> None:
    """Clear all state (in-process map + memoized Redis client) for tests."""
    global _redis_client, _redis_init_attempted
    with _lock:
        _local.clear()
    _redis_client = None
    _redis_init_attempted = False
