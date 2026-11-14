import os

from app.auth.replit_auth import (
    create_session_token,
    get_current_user_from_session,
    replit_auth,
    save_or_update_user,
)
from app.security.config import secure_cookies_enabled
from app.security.cookies import clear_auth_cookies, set_auth_cookies
from app.services.security_audit_service import record_security_event
from app.services.session_service import revoke_session
from app.utils.auth_utils import get_current_token_payload_optional
from app.utils.logger import logger
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/auth", tags=["auth"])
AUTH_NEXT_URL_COOKIE = "auth_next_url"
AUTH_OAUTH_STATE_COOKIE = "auth_oauth_state"
AUTH_OAUTH_VERIFIER_COOKIE = "auth_oauth_verifier"
AUTH_OAUTH_COOKIE_MAX_AGE = 600


def _set_auth_flow_cookie(response: Response, request: Request, key: str, value: str) -> None:
    response.set_cookie(
        key,
        value,
        httponly=True,
        max_age=AUTH_OAUTH_COOKIE_MAX_AGE,
        secure=secure_cookies_enabled(request),
        samesite="lax",
        path="/",
    )


def _clear_auth_flow_cookies(response: Response, request: Request) -> None:
    secure = secure_cookies_enabled(request)
    for key in (AUTH_NEXT_URL_COOKIE, AUTH_OAUTH_STATE_COOKIE, AUTH_OAUTH_VERIFIER_COOKIE):
        response.delete_cookie(key=key, path="/", secure=secure, samesite="lax")


def get_base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}"

    replit_domain = os.environ.get("REPLIT_DEV_DOMAIN")
    if replit_domain:
        return f"https://{replit_domain}"

    replit_domains = os.environ.get("REPLIT_DOMAINS")
    if replit_domains:
        return f"https://{replit_domains}"

    return str(request.base_url).rstrip("/")


def get_frontend_auth_url(request: Request, query: str = "") -> str:
    base_url = get_base_url(request)
    return f"{base_url}/auth{query}"


@router.get("/login")
async def login(request: Request):
    if not replit_auth.client_id:
        logger.warning("[Auth] OAuth login requested without REPL_ID configured")
        return RedirectResponse(url=get_frontend_auth_url(request, "?oauth_error=not_configured"))

    base_url = get_base_url(request)
    redirect_uri = f"{base_url}/auth/callback"

    next_url = request.query_params.get("next", "/")

    login_url, state, code_verifier = replit_auth.prepare_login(redirect_uri)

    response = RedirectResponse(url=login_url)
    _set_auth_flow_cookie(response, request, AUTH_NEXT_URL_COOKIE, next_url)
    _set_auth_flow_cookie(response, request, AUTH_OAUTH_STATE_COOKIE, state)
    _set_auth_flow_cookie(response, request, AUTH_OAUTH_VERIFIER_COOKIE, code_verifier)
    return response


@router.get("/callback")
async def callback(request: Request, response: Response):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        logger.error(f"[Auth] OAuth error: {error}")
        return RedirectResponse(url="/?error=auth_failed")

    if not code or not state:
        logger.error("[Auth] Missing code or state in callback")
        return RedirectResponse(url="/?error=invalid_callback")

    base_url = get_base_url(request)
    redirect_uri = f"{base_url}/auth/callback"

    expected_state = request.cookies.get(AUTH_OAUTH_STATE_COOKIE)
    code_verifier = request.cookies.get(AUTH_OAUTH_VERIFIER_COOKIE)
    if not expected_state or expected_state != state or not code_verifier:
        logger.error("[Auth] OAuth callback state/verifier mismatch")
        invalid_response = RedirectResponse(url="/?error=invalid_callback")
        _clear_auth_flow_cookies(invalid_response, request)
        return invalid_response

    token_response = await replit_auth.exchange_code(code, code_verifier, redirect_uri)

    if not token_response:
        logger.error("[Auth] Failed to exchange code for tokens")
        error_response = RedirectResponse(url="/?error=token_exchange_failed")
        _clear_auth_flow_cookies(error_response, request)
        return error_response

    id_token = token_response.get("id_token")
    if not id_token:
        logger.error("[Auth] No ID token in response")
        return RedirectResponse(url="/?error=no_id_token")

    claims = replit_auth.decode_id_token(id_token)
    if not claims:
        logger.error("[Auth] Failed to decode ID token")
        return RedirectResponse(url="/?error=invalid_token")

    try:
        user_id = save_or_update_user(claims)
    except Exception as e:
        logger.error(f"[Auth] Failed to save user: {e}")
        return RedirectResponse(url="/?error=user_save_failed")

    session_token = create_session_token(
        user_id=user_id,
        replit_id=str(claims.get("sub")),
        email=claims.get("email"),
        request=request,
    )

    next_url = request.cookies.get(AUTH_NEXT_URL_COOKIE, "/")

    redirect_response = RedirectResponse(url=next_url)
    set_auth_cookies(redirect_response, session_token, request)
    _clear_auth_flow_cookies(redirect_response, request)

    logger.info(f"[Auth] User logged in successfully: {user_id}")
    return redirect_response


@router.get("/logout")
async def logout(request: Request):
    base_url = get_base_url(request)
    payload = get_current_token_payload_optional(request)
    user_id = str(payload.get("sub") or "") if payload else None
    session_id = str(payload.get("sid") or "") if payload else None
    if replit_auth.client_id:
        redirect_url = replit_auth.get_logout_url(base_url)
    else:
        logger.info("[Auth] Local logout requested without REPL_ID configured")
        redirect_url = get_frontend_auth_url(request)

    response = RedirectResponse(url=redirect_url)
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
            target_id=str(session_id) if session_id else None,
            outcome="success",
        )
    clear_auth_cookies(response, request)

    logger.info("[Auth] User logged out")
    return response


@router.get("/me")
async def get_current_user(request: Request):
    session = get_current_user_from_session(request)

    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {
        "user_id": session.get("sub"),
        "replit_id": session.get("replit_id"),
        "email": session.get("email"),
    }


@router.get("/status")
async def auth_status(request: Request):
    session = get_current_user_from_session(request)
    return {
        "authenticated": session is not None,
        "user_id": session.get("sub") if session else None,
    }
