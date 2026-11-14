"""Only accept traffic that came through the Cloudflare edge Worker.

When ``EDGE_SHARED_SECRET`` is set, every HTTP and WebSocket request must
carry a matching ``X-Manifest-Edge`` header, which the Worker in
``deploy/cloudflare`` adds. Health probes stay open for the host's checks.
This stops anyone from bypassing the edge by calling the origin hostname
directly, which also makes the forwarded client IP set by the Worker
trustworthy. When the variable is unset (local development, tests), the
guard does nothing.
"""

from __future__ import annotations

import hmac
import os

EDGE_HEADER = b"x-manifest-edge"
OPEN_PATHS = frozenset({"/ping", "/health", "/healthz"})


class EdgeGuardMiddleware:
    def __init__(self, app, secret: str | None = None):
        self.app = app
        self.secret = (
            secret if secret is not None else os.getenv("EDGE_SHARED_SECRET", "")
        ).strip()

    async def __call__(self, scope, receive, send):
        if not self.secret or scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        if scope.get("path") in OPEN_PATHS:
            return await self.app(scope, receive, send)
        provided = b""
        for name, value in scope.get("headers") or []:
            if name == EDGE_HEADER:
                provided = value
                break
        if hmac.compare_digest(provided, self.secret.encode()):
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4403})
            return
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"error":"forbidden"}'})
        return
