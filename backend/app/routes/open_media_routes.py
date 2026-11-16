"""Open Media linking (OAuth 2.1 + PKCE) and its signed webhooks.

- ``GET  /api/integrations/open-media/connect``  — signed-in full account → Open Media ``/authorize``
- ``GET  /api/integrations/open-media/callback`` — code exchange, then back to ``/account``
- ``POST /api/webhooks/open-media``              — HMAC-signed, IDs-only events
"""

from __future__ import annotations

from urllib.parse import urlencode

from app.auth.current_user import get_current_user_id_optional
from app.db.database import create_database_client
from app.services.identity.guest_workspace import fetch_user_is_guest
from app.services.integrations.open_media import identity, settings, webhooks
from app.services.integrations.open_media.client import OpenMediaError
from app.utils.logger import logger
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

router = APIRouter(tags=["open-media"])

_ACCOUNT_PATH = "/account"


def _account_redirect(result: str) -> RedirectResponse:
    query = urlencode({"open_media": result})
    return RedirectResponse(f"{_ACCOUNT_PATH}?{query}#open-media", status_code=303)


def _login_redirect() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


@router.get("/api/integrations/open-media/connect", include_in_schema=False)
def connect_open_media(request: Request):
    if not settings.enabled():
        return _account_redirect("disabled")
    user_id = get_current_user_id_optional(request)
    if not user_id:
        return _login_redirect()
    db = create_database_client()
    if fetch_user_is_guest(db, str(user_id)):
        return _account_redirect("full_account_required")
    # Pre-fills the Open Media sign-in with the email the person already uses here.
    return RedirectResponse(
        identity.authorize_url(str(user_id), login_hint=_account_email(db, str(user_id))),
        status_code=303,
    )


def _account_email(db, user_id: str) -> str | None:
    try:
        row = db.table("users").select("email").eq("user_id", user_id).single().execute().data
    except Exception as exc:  # the hint is a convenience; connecting works without it
        logger.info("[open_media] no login hint: %s", type(exc).__name__)
        return None
    email = (row or {}).get("email") if isinstance(row, dict) else None
    return email.strip().lower() if isinstance(email, str) and "@" in email else None


@router.get("/api/integrations/open-media/callback", include_in_schema=False)
def open_media_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if not settings.enabled():
        return _account_redirect("disabled")
    user_id = get_current_user_id_optional(request)
    if not user_id:
        return _login_redirect()
    if error or not code or not state:
        return _account_redirect("cancelled" if error == "access_denied" else "error")
    try:
        identity.complete_link(str(user_id), code=code, state=state)
    except identity.OpenMediaLinkError as exc:
        logger.info("[open_media] link failed: %s", exc)
        return _account_redirect("error")

    from app.services.pitch_reels.video_worker import resume_reels_waiting_for_open_media

    try:
        resume_reels_waiting_for_open_media(str(user_id))
    except Exception as exc:  # the link itself succeeded
        logger.warning("[open_media] could not resume pending reels: %s", type(exc).__name__)
    return _account_redirect("linked")


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
