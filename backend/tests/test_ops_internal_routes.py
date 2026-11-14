"""Tests for internal ops snapshot route."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import fastapi_app


def test_ops_snapshot_requires_agent_key():
    client = TestClient(fastapi_app)
    with patch.dict("os.environ", {"MANIFEST_AGENT_LOOP_SECRET": "loop-secret"}):
        r401 = client.get("/api/internal/ops/snapshot")
    assert r401.status_code == 401


def test_ops_snapshot_returns_pool_and_queue_placeholder():
    client = TestClient(fastapi_app)
    with patch.dict("os.environ", {"MANIFEST_AGENT_LOOP_SECRET": "loop-secret"}):
        resp = client.get(
            "/api/internal/ops/snapshot",
            headers={"X-Manifest-Agent-Key": "loop-secret"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "db_pool" in body
    assert "async_db_pool" in body
    assert "pooled_connections_checked_out" in body["db_pool"]
    assert body["graphql_slow_request_threshold_ms"] >= 0
    assert body["background_job_queue"]["status"] == "not_implemented"
