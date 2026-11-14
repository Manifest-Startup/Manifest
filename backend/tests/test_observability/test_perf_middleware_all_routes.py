"""Stage #1 — performance_metrics_middleware on all routes.

Pre-Stage-1 the perf middleware only emitted ``X-Manifest-*`` headers on
``/graphql``. After Stage 1 it emits them on every route except health
checks, so we can size connection pools and spot N+1 patterns in REST
handlers (e.g. ``/api/v1/...``, OAuth redirects, etc.).

Tests:

* REST endpoint receives ``X-Manifest-Duration-Ms`` + DB counters.
* GraphQL endpoint still receives the backward-compatible
  ``X-Manifest-GraphQL-Duration-Ms`` alias.
* ``/ping`` and ``/metrics`` are NOT instrumented (excluded set).
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi.testclient import TestClient

# Importing app.main triggers the full middleware stack registration.
from app.main import app

client = TestClient(app)


def test_ping_is_not_instrumented():
    response = client.get("/ping")
    assert response.status_code == 200
    assert "X-Manifest-Duration-Ms" not in response.headers
    # The X-Request-Id header IS expected on every route (outermost MW).
    assert "X-Request-Id" in response.headers


def test_rest_root_emits_duration_and_db_counters():
    response = client.get("/")
    # Root may return SPA HTML or the API JSON; either way the perf
    # middleware should have stamped the headers.
    assert "X-Manifest-Duration-Ms" in response.headers
    assert "X-Manifest-DB-Query-Count" in response.headers
    assert "X-Manifest-DB-Connection-Count" in response.headers

    duration = float(response.headers["X-Manifest-Duration-Ms"])
    assert duration >= 0
    int(response.headers["X-Manifest-DB-Query-Count"])  # parses as int
    int(response.headers["X-Manifest-DB-Connection-Count"])


def test_request_id_is_present_on_all_routes():
    for path in ["/", "/ping", "/api/docs"]:
        response = client.get(path)
        rid = response.headers.get("X-Request-Id")
        assert rid, f"missing X-Request-Id on {path}"
        assert len(rid) >= 8


def test_graphql_keeps_backward_compatible_header():
    """The legacy X-Manifest-GraphQL-Duration-Ms alias must still appear.

    Any existing consumer (e.g. Apollo Studio integration, frontend perf
    logger) that parses that exact header continues to work post-Stage-1.
    """
    response = client.post(
        "/graphql",
        json={"query": "{ __typename }"},
        headers={"Content-Type": "application/json"},
    )
    # /graphql may 401 without auth, but the perf middleware runs before
    # auth, so headers are stamped regardless.
    assert "X-Manifest-Duration-Ms" in response.headers
    assert "X-Manifest-GraphQL-Duration-Ms" in response.headers
    duration = float(response.headers["X-Manifest-GraphQL-Duration-Ms"])
    assert duration >= 0
