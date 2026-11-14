"""Stage #1 — RequestIDMiddleware.

Validates the four invariants documented in
``backend/app/middleware/request_id.py``:

1. Every response carries an ``X-Request-Id`` header.
2. An incoming ``X-Request-Id`` is honored verbatim (within size bound).
3. Each unsolicited request gets a *unique* generated ID.
4. ``get_request_id()`` is readable from inside a route handler.
"""

import os
import sys
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.middleware import REQUEST_ID_HEADER, RequestIDMiddleware, get_request_id


def _build_app() -> TestClient:
    """Minimal app with ONLY the middleware under test — no other side effects."""
    app = FastAPI()

    @app.get("/echo")
    async def echo():
        return {"request_id_in_handler": get_request_id()}

    app.add_middleware(RequestIDMiddleware)
    return TestClient(app)


def test_generates_request_id_when_absent():
    client = _build_app()
    response = client.get("/echo")

    assert response.status_code == 200
    rid = response.headers.get(REQUEST_ID_HEADER)
    assert rid, "every response must carry an X-Request-Id"
    assert len(rid) == 32, "generated IDs use uuid4().hex (32-char hex)"
    int(rid, 16)  # raises if not hex
    assert response.json()["request_id_in_handler"] == rid


def test_honors_incoming_request_id():
    client = _build_app()
    upstream_id = "trace-from-cloudflare-abc123"
    response = client.get("/echo", headers={"X-Request-Id": upstream_id})

    assert response.headers[REQUEST_ID_HEADER] == upstream_id
    assert response.json()["request_id_in_handler"] == upstream_id


def test_truncates_excessively_long_incoming_id():
    client = _build_app()
    too_long = "a" * 500
    response = client.get("/echo", headers={"X-Request-Id": too_long})

    rid = response.headers[REQUEST_ID_HEADER]
    assert len(rid) == 128, "incoming ID must be clamped at 128 chars"
    assert rid == "a" * 128


def test_generated_ids_are_unique_across_requests():
    client = _build_app()
    ids = {client.get("/echo").headers[REQUEST_ID_HEADER] for _ in range(8)}
    assert len(ids) == 8, "uuid4 should give us 8 distinct IDs"


def test_get_request_id_is_none_outside_a_request():
    # No request in flight on this thread -> ContextVar default is None.
    assert get_request_id() is None


def test_request_id_isolated_between_sequential_requests():
    client = _build_app()
    a = client.get("/echo").json()["request_id_in_handler"]
    b = client.get("/echo").json()["request_id_in_handler"]
    assert a != b
    # After both requests finish, the ContextVar must NOT leak into this thread.
    assert get_request_id() is None


def test_honors_lowercase_header_casing():
    """ASGI lowercases all header names; ensure we match on bytes correctly."""
    client = _build_app()
    rid = uuid.uuid4().hex
    response = client.get("/echo", headers={"x-request-id": rid})
    assert response.headers[REQUEST_ID_HEADER] == rid
