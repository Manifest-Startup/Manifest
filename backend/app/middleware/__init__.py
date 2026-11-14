"""HTTP middleware for the Manifest FastAPI app.

Centralized so the wiring in ``app.main`` stays a one-liner per concern.
See ``docs/OBSERVABILITY_AND_SLO.md`` for what these emit.
"""

from app.middleware.request_id import (
    REQUEST_ID_HEADER,
    RequestIDMiddleware,
    get_request_id,
)

__all__ = [
    "REQUEST_ID_HEADER",
    "RequestIDMiddleware",
    "get_request_id",
]
