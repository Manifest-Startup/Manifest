"""Open Media's signed webhooks (``POST /api/webhooks/open-media``, HMAC-signed, IDs only).

Signing in with Open Media (which also links the account) lives in ``auth_routes``.
"""

from __future__ import annotations

from app.services.integrations.open_media import webhooks
from app.services.integrations.open_media.client import OpenMediaError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["open-media"])


@router.post("/api/webhooks/open-media", include_in_schema=False)
async def open_media_webhook(request: Request):
    raw = await request.body()
    try:
        result = webhooks.handle(
            raw,
            event=request.headers.get("x-open-media-event"),
            timestamp=request.headers.get("x-open-media-timestamp"),
            signature=request.headers.get("x-open-media-signature"),
        )
    except webhooks.WebhookRejected as exc:
        return JSONResponse({"error": "rejected", "error_description": str(exc)}, exc.status)
    except OpenMediaError:  # pragma: no cover - handlers only touch the local cache
        return JSONResponse({"error": "unavailable"}, 503)
    return JSONResponse(result)
