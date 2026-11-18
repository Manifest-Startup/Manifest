"""Sign in with Open Media, and sign out.

- ``GET  /api/auth/open-media/start?next=/ideas`` — no session needed; sets the signed
  nonce cookie and redirects to Open Media ``/authorize`` (PKCE, signed state)
- ``GET  /api/auth/open-media/callback``          — finds or creates the Manifest user,
  merges the guest workspace, sets the session cookie, redirects to ``next``
- ``POST /api/auth/logout``                        — revokes this session, clears cookies

Open Media is Manifest's only identity provider (ADR 0002). Failures redirect to
``/login?error=<code>`` so the login page can explain what happened.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode, urlsplit

from app.auth.current_user import (
    DEMO_MODE,
    DEMO_USER_EMAIL,
    DEMO_USER_ID,
    create_session_token,
    generate_demo_token,
    get_current_token_payload_optional,
    get_current_user_id_optional,
)
from app.db.database import create_database_client
from app.security.audit_detections import detect_brute_force, detect_impossible_travel
from app.security.cookies import (
    SIGN_IN_NONCE_COOKIE_NAME,
    clear_auth_cookies,
    clear_sign_in_nonce_cookie,
    set_auth_cookies,
    set_sign_in_nonce_cookie,
)
from app.services.compliance.security_audit import record_security_event
from app.services.identity.guest_workspace import claim_guest_workspace, fetch_user_is_guest
from app.services.identity.sessions import revoke_session
from app.services.integrations.open_media import identity
from app.utils.logger import logger
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

DEFAULT_NEXT = "/ideas"
LOGIN_PATH = "/login"
# The one backend page sign-in may return to: the Manifest CLI approval (ADR 0003).
CLI_AUTHORIZE_PATH = "/api/cli/authorize"
# Approval pages people come back to after signing in: the CLI (ADR 0003) and AI agents (ADR 0004).
APPROVAL_PATHS = frozenset({CLI_AUTHORIZE_PATH, "/api/oauth/authorize"})
APPROVAL_NEXT_MAX = 4096  # agent requests carry a signed client_id
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,63}$")


def safe_next(raw: str | None) -> str:
    """A same-origin path to return to after sign-in; anything else becomes ``/ideas``.

    Rejects absolute and scheme-relative URLs (``//evil``, ``/\\evil``), control
    characters, and the login page itself.
    """
    value = (raw or "").strip()
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        return DEFAULT_NEXT
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value) or len(value) > APPROVAL_NEXT_MAX:
        return DEFAULT_NEXT
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return DEFAULT_NEXT
    if parts.path in APPROVAL_PATHS:
        return value
    if len(value) > 512:
        return DEFAULT_NEXT
    if parts.path in {LOGIN_PATH, "/auth", "/signup"} or parts.path.startswith("/api/"):
        return DEFAULT_NEXT
    return value


def _login_error(code: str) -> RedirectResponse:
    return RedirectResponse(f"{LOGIN_PATH}?{urlencode({'error': code})}", status_code=303)


def _client_ip(request: Request) -> str | None:
    client = getattr(request, "client", None)
    return getattr(client, "host", None) if client else None


def _ensure_demo_user() -> None:
    """Demo mode keeps users in the in-memory database; make sure the demo user exists."""
    db = create_database_client()
    try:
        existing = db.table("users").select("user_id").eq("user_id", DEMO_USER_ID).execute().data
        if not existing:
            db.table("users").insert(
                {
                    "user_id": DEMO_USER_ID,
                    "email": DEMO_USER_EMAIL,
                    "username": DEMO_USER_EMAIL.split("@")[0],
                    "auth_provider": "demo",
                }
            ).execute()
    except Exception as exc:  # best effort: the demo session works without the row
        logger.warning("[auth] could not create the demo user: %s", type(exc).__name__)


def _user_email(user_id: str) -> str | None:
    try:
        row = (
            create_database_client()
            .table("users")
            .select("email")
            .eq("user_id", user_id)
            .single()
            .execute()
            .data
        )
    except Exception as exc:  # the hint is a convenience; signing in works without it
        logger.info("[auth] no login hint: %s", type(exc).__name__)
        return None
    email = (row or {}).get("email") if isinstance(row, dict) else None
    return email.strip().lower() if isinstance(email, str) and "@" in email else None


@router.get("/open-media/start", include_in_schema=False)
def open_media_start(request: Request, next: str | None = None, login_hint: str | None = None):
    next_path = safe_next(next)
    if DEMO_MODE:
        # Local development without a database or Open Media: sign in the demo user.
        _ensure_demo_user()
        response = RedirectResponse(next_path, status_code=303)
        set_auth_cookies(response, generate_demo_token(DEMO_USER_ID, DEMO_USER_EMAIL), request)
        return response

    user_id = get_current_user_id_optional(request)
    guest_user_id = None
    reconnect_user_id = None
    hint = (login_hint or "").strip().lower() or None
    if user_id:
        if fetch_user_is_guest(create_database_client(), str(user_id)):
            guest_user_id = str(user_id)
        else:
            reconnect_user_id = str(user_id)
            hint = _user_email(str(user_id)) or hint
    if hint and not _EMAIL.match(hint):
        hint = None

    url, nonce = identity.authorize_url(
        next_path=next_path,
        guest_user_id=guest_user_id,
        user_id=reconnect_user_id,
        login_hint=hint,
    )
    response = RedirectResponse(url, status_code=303)
    set_sign_in_nonce_cookie(response, identity.nonce_cookie_value(nonce), request)
    return response


@router.get("/open-media/callback", include_in_schema=False)
def open_media_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error or not code or not state:
        response = _login_error("cancelled" if error == "access_denied" else "failed")
        clear_sign_in_nonce_cookie(response, request)
        return response

    session_user_id = get_current_user_id_optional(request)
    try:
        result = identity.complete_sign_in(
            code=code,
            state=state,
            nonce_cookie=request.cookies.get(SIGN_IN_NONCE_COOKIE_NAME),
            session_user_id=str(session_user_id) if session_user_id else None,
        )
    except identity.OpenMediaLinkError as exc:
        logger.info("[auth] Open Media sign-in refused: %s", exc.code)
        record_security_event(
            "login_failed",
            request_ip=_client_ip(request),
            actor_type="anonymous",
            action="login",
            target_type="user",
            outcome="failed",
            user_agent=request.headers.get("user-agent"),
            metadata={"provider": "open_media", "reason": exc.code},
        )
        detect_brute_force(user_id=None, request_ip=_client_ip(request))
        response = _login_error(exc.code)
        clear_sign_in_nonce_cookie(response, request)
        return response

    merged = 0
    if result.guest_user_id:
        try:
            merged = claim_guest_workspace(result.user_id, result.guest_user_id)
        except Exception as exc:  # sign-in still succeeds; the guest row keeps its TTL
            logger.warning("[auth] guest workspace merge failed: %s", exc)

    token = create_session_token(result.user_id, email=result.email, request=request)
    next_path = result.next_path
    if merged:
        joiner = "&" if "?" in next_path else "?"
        next_path = f"{next_path}{joiner}{urlencode({'merged': merged})}"
    response = RedirectResponse(next_path, status_code=303)
    set_auth_cookies(response, token, request)
    clear_sign_in_nonce_cookie(response, request)
    record_security_event(
        "signup_success" if result.matched_by == "new" else "login_success",
        user_id=result.user_id,
        request_ip=_client_ip(request),
        actor_id=result.user_id,
        actor_type="user",
        action="signup" if result.matched_by == "new" else "login",
        target_type="user",
        target_id=result.user_id,
        outcome="success",
        user_agent=request.headers.get("user-agent"),
        metadata={
            "provider": "open_media",
            "matched_by": result.matched_by,
            "guest_ideas_merged": merged,
        },
    )
    detect_impossible_travel(user_id=result.user_id, request_ip=_client_ip(request))
    _resume_pending_reels(result.user_id)
    return response


def _resume_pending_reels(user_id: str) -> None:
    from app.services.pitch_reels.video_worker import resume_reels_waiting_for_open_media

    try:
        resume_reels_waiting_for_open_media(user_id)
    except Exception as exc:  # the sign-in itself succeeded
        logger.warning("[auth] could not resume pending reels: %s", type(exc).__name__)


@router.post("/logout", include_in_schema=False)
def logout(request: Request):
    payload = get_current_token_payload_optional(request) or {}
    user_id = str(payload.get("sub") or "")
    session_id = str(payload.get("sid") or "")
    if user_id and session_id:
        revoke_session(session_id, user_id)
        record_security_event(
            "logout",
            user_id=user_id,
            session_id=session_id,
            actor_id=user_id,
            actor_type="user",
            action="logout",
            target_type="session",
            target_id=session_id,
            outcome="success",
            user_agent=request.headers.get("user-agent"),
        )
    response = JSONResponse({"ok": True})
    clear_auth_cookies(response, request)
    return response
