"""Per-request stable correlation ID — Stage #1 of the backend migration.

Why this exists
---------------
The pre-Stage-1 backend logs as plain text with no correlation: a single
GraphQL mutation that fans out to 6–11 LLM calls and a dozen DB queries
emits log lines that cannot be stitched back together when something goes
wrong in production. This middleware fixes that by:

1. Honoring any upstream ``X-Request-Id`` (set by Cloudflare / Render's
   edge / a browser dev tool / a chained service) so traces survive hops.
2. Generating a 32-char hex UUID4 when no upstream ID is present.
3. Binding the ID to a ``ContextVar`` so loggers, GraphQL resolvers, and
   ``asyncio``-spawned background tasks can read it without explicit
   plumbing.
4. Echoing the ID back on the response (even error responses) so a user
   reporting a bug can quote it.
5. Resetting the ContextVar in a ``finally`` so the ID cannot leak into
   the next request handled by the same Uvicorn worker.

Pure stdlib — no new dependency.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterable
from contextvars import ContextVar
from typing import Any

REQUEST_ID_HEADER = "X-Request-Id"
_REQUEST_ID_HEADER_BYTES = b"x-request-id"
_REQUEST_ID_MAX_LEN = 128

_request_id_ctx: ContextVar[str | None] = ContextVar("manifest_request_id", default=None)


def get_request_id() -> str | None:
    """Return the request ID bound to the current task/request, if any.

    Safe to call from anywhere — returns ``None`` outside an HTTP request
    (e.g. in startup hooks, background threads not seeded with the ctx).
    """

    return _request_id_ctx.get()


def _normalize_incoming(raw: bytes) -> str:
    text = raw.decode("latin-1", errors="replace").strip()
    if not text:
        return ""
    # Bound the length so a malicious upstream cannot blow up log lines.
    return text[:_REQUEST_ID_MAX_LEN]


def _extract_incoming(headers: Iterable[tuple[bytes, bytes]]) -> str:
    for name, value in headers:
        if name == _REQUEST_ID_HEADER_BYTES:
            return _normalize_incoming(value)
    return ""


class RequestIDMiddleware:
    """Pure-ASGI middleware — assigns ``X-Request-Id`` to every HTTP request.

    Register LAST in ``main.py`` so it becomes the OUTERMOST middleware:
    the ContextVar is set before any other middleware runs, and the
    response header is appended after every other middleware has finished.
    """

    def __init__(self, app: Callable[..., Awaitable[Any]]):
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        incoming = _extract_incoming(scope.get("headers", []))
        rid = incoming or uuid.uuid4().hex
        rid_bytes = rid.encode("latin-1")
        token = _request_id_ctx.set(rid)

        async def send_with_request_id(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Avoid duplicate header if a handler explicitly wrote one.
                if not any(name == _REQUEST_ID_HEADER_BYTES for name, _ in headers):
                    headers.append((_REQUEST_ID_HEADER_BYTES, rid_bytes))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _request_id_ctx.reset(token)
