"""Tests for the Phase 4 cache service.

Covers the in-process fallback (REDIS_URL unset — the default, behaviour-
preserving path) and the Redis path via an injected fake client, without a real
Redis server.
"""

from __future__ import annotations

import json

import pytest
from app.services import cache_service as cs


@pytest.fixture(autouse=True)
def _clean_cache():
    cs._reset_for_tests()
    yield
    cs._reset_for_tests()


# ---------- in-process fallback (REDIS_URL unset) ----------


def test_backend_is_memory_without_redis_url(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    cs._reset_for_tests()
    assert cs.cache_backend() == "memory"


def test_set_get_roundtrip_memory(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    cs._reset_for_tests()
    cs.cache_set("k1", {"a": 1}, 60)
    assert cs.cache_get("k1") == {"a": 1}


def test_get_miss_returns_none(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    cs._reset_for_tests()
    assert cs.cache_get("absent") is None


def test_expiry_evicts(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    cs._reset_for_tests()
    now = [1000.0]
    monkeypatch.setattr(cs.time, "time", lambda: now[0])
    cs.cache_set("k", "v", 10)
    now[0] = 1009.0
    assert cs.cache_get("k") == "v"
    now[0] = 1011.0
    assert cs.cache_get("k") is None


def test_delete_memory(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    cs._reset_for_tests()
    cs.cache_set("k", "v", 60)
    cs.cache_delete("k")
    assert cs.cache_get("k") is None


def test_ttl_floored_to_one_second(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    cs._reset_for_tests()
    # ttl <= 0 must not raise and must still store briefly.
    cs.cache_set("k", "v", 0)
    assert cs.cache_get("k") == "v"


# ---------- Redis path (fake client) ----------


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.ex: dict[str, int] = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        if ex is not None:
            self.ex[key] = ex

    def delete(self, key):
        self.store.pop(key, None)


def _use_fake_redis(monkeypatch, fake):
    monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
    cs._reset_for_tests()
    monkeypatch.setattr(cs, "_get_redis", lambda: fake)


def test_backend_is_redis_when_client_present(monkeypatch):
    _use_fake_redis(monkeypatch, _FakeRedis())
    assert cs.cache_backend() == "redis"


def test_redis_roundtrip_serializes_json(monkeypatch):
    fake = _FakeRedis()
    _use_fake_redis(monkeypatch, fake)
    cs.cache_set("k", {"hello": "world"}, 30)
    # stored as JSON, with a TTL applied
    assert json.loads(fake.store["k"]) == {"hello": "world"}
    assert fake.ex["k"] == 30
    assert cs.cache_get("k") == {"hello": "world"}


def test_redis_errors_degrade_to_miss(monkeypatch):
    class _BoomRedis(_FakeRedis):
        def get(self, key):
            raise RuntimeError("connection lost")

        def set(self, key, value, ex=None):
            raise RuntimeError("connection lost")

    _use_fake_redis(monkeypatch, _BoomRedis())
    # set swallows the error, get returns a miss — never raises.
    cs.cache_set("k", "v", 30)
    assert cs.cache_get("k") is None
