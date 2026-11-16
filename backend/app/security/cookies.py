import secrets

from app.security.config import secure_cookies_enabled
from fastapi import Request, Response

SESSION_COOKIE_NAME = "session_token"
LEGACY_ACCESS_COOKIE_NAME = "access_token"
CSRF_COOKIE_NAME = "manifest_csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def _cookie_common_kwargs(request: Request | None) -> dict:
    return {
        "httponly": True,
        "secure": secure_cookies_enabled(request),
        "samesite": "lax",
        "path": "/",
        "max_age": SESSION_MAX_AGE_SECONDS,
    }


def ensure_csrf_cookie(response: Response, request: Request | None) -> str:
    existing = request.cookies.get(CSRF_COOKIE_NAME) if request else None
    token = existing or secrets.token_urlsafe(32)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        secure=secure_cookies_enabled(request),
        samesite="lax",
        path="/",
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    return token


def set_auth_cookies(response: Response, token: str, request: Request | None) -> None:
    kwargs = _cookie_common_kwargs(request)
    response.set_cookie(key=SESSION_COOKIE_NAME, value=token, **kwargs)
    # Transitional legacy alias for clients/routes that still reference access_token.
    response.set_cookie(key=LEGACY_ACCESS_COOKIE_NAME, value=token, **kwargs)
    ensure_csrf_cookie(response, request)


def clear_auth_cookies(response: Response, request: Request | None = None) -> None:
    secure = secure_cookies_enabled(request)
    for key in (SESSION_COOKIE_NAME, LEGACY_ACCESS_COOKIE_NAME, CSRF_COOKIE_NAME):
        response.delete_cookie(key=key, path="/", secure=secure, samesite="lax")


# "Continue with Open Media": a short-lived, HttpOnly nonce cookie binds the
# OAuth ``state`` to the browser that started the sign-in (login CSRF guard).
SIGN_IN_NONCE_COOKIE_NAME = "manifest_om_signin"
SIGN_IN_NONCE_COOKIE_PATH = "/api/auth/open-media"
SIGN_IN_NONCE_MAX_AGE_SECONDS = 10 * 60


def set_sign_in_nonce_cookie(response: Response, value: str, request: Request | None) -> None:
    response.set_cookie(
        key=SIGN_IN_NONCE_COOKIE_NAME,
        value=value,
        httponly=True,
        secure=secure_cookies_enabled(request),
        samesite="lax",
        path=SIGN_IN_NONCE_COOKIE_PATH,
        max_age=SIGN_IN_NONCE_MAX_AGE_SECONDS,
    )


def clear_sign_in_nonce_cookie(response: Response, request: Request | None = None) -> None:
    response.delete_cookie(
        key=SIGN_IN_NONCE_COOKIE_NAME,
        path=SIGN_IN_NONCE_COOKIE_PATH,
        secure=secure_cookies_enabled(request),
        samesite="lax",
    )
