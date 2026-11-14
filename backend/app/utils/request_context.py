"""The current request's ID, readable from anywhere (logs, resolvers, services).

:class:`app.middleware.request_id.RequestIDMiddleware` sets it for each HTTP
request; outside a request it is ``None``.
"""

from __future__ import annotations

from contextvars import ContextVar

_request_id_ctx: ContextVar[str | None] = ContextVar("manifest_request_id", default=None)


def get_request_id() -> str | None:
    """The request ID bound to the current task, or ``None`` outside an HTTP request."""
    return _request_id_ctx.get()
