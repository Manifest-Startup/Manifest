"""CSRF defence for cookie-signed-in GraphQL writes: the request must come from Manifest itself.

The web app signs in with an HttpOnly session cookie (SameSite=Lax). A page on another site
can't read Manifest's answers (CORS), but a browser would still attach the cookie to a
request that page sends. So a ``POST /graphql`` that carries the session cookie and no
``Authorization`` header is accepted only when its ``Origin`` (or, without one, ``Referer``)
is an allowed Manifest origin or the request's own host, and, when the browser holds the
``manifest_csrf_token`` cookie, carries the same value in ``X-CSRF-Token`` (double submit). Browsers always send ``Origin`` on
cross-site POSTs, so a forged request is refused. A request with no browser origin at all
(curl, scripts) carries no victim's cookie, so it is not a CSRF vector and passes.

Bearer-token clients (CLI, MCP, voice, iOS) send ``Authorization`` and are unaffected. Only
``/graphql`` is checked: cross-site POSTs that are legitimate by design (SAML assertions,
signed webhooks) live elsewhere and have their own guards.
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Iterable
from http.cookies import CookieError, SimpleCookie
from typing import Any
from urllib.parse import urlsplit

from app.utils.logger import logger

SESSION_COOKIES = ("session_token=", "access_token=")
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_COOKIE = "manifest_csrf_token"  # app.security.cookies.CSRF_COOKIE_NAME


def _cookie_value(header: str, name: str) -> str:
    try:
        jar = SimpleCookie()
        jar.load(header)
    except CookieError:
        return ""
    morsel = jar.get(name)
    return morsel.value if morsel else ""


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}".lower()


class OriginCheckMiddleware:
    def __init__(
        self, app: Any, allowed_origins: Iterable[str], *, paths: tuple[str, ...] = ("/graphql",)
    ) -> None:
        self.app = app
        self.allowed = {o.rstrip("/").lower() for o in allowed_origins}
        self.paths = paths

    def _applies(self, scope: dict[str, Any]) -> bool:
        return (
            scope.get("type") == "http"
            and scope.get("method") in UNSAFE_METHODS
            and any(scope.get("path", "").startswith(p) for p in self.paths)
        )

    def allowed_request(self, headers: dict[str, str]) -> bool:
        cookie = headers.get("cookie", "")
        if headers.get("authorization") or not any(name in cookie for name in SESSION_COOKIES):
            return True  # not signed in by cookie: nothing a forged request could ride on
        # Double submit: when the browser holds the CSRF cookie (issued with every sign-in),
        # the app echoes it in X-CSRF-Token; a page on another site can't read it to do so.
        expected = _cookie_value(cookie, CSRF_COOKIE)
        if expected and not hmac.compare_digest(
            expected.encode(), (headers.get("x-csrf-token") or "").encode()
        ):
            return False
        origin = headers.get("origin", "")
        if origin == "null":
            return False
        source = origin.lower() or _origin_of(headers.get("referer", ""))
        if not source:
            return True  # not a browser request
        host = headers.get("x-forwarded-host") or headers.get("host") or ""
        scheme = headers.get("x-forwarded-proto") or "https"
        own = f"{scheme}://{host}".lower() if host else ""
        return source in self.allowed or (bool(own) and source == own)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if not self._applies(scope):
            await self.app(scope, receive, send)
            return
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        if self.allowed_request(headers):
            await self.app(scope, receive, send)
            return
        logger.warning(
            "[security] cross-site write refused",
            extra={
                "http.request.header.origin": headers.get("origin", "")[:200],
                "url.path": scope.get("path"),
            },
        )
        body = json.dumps(
            {"errors": [{"message": "This request didn't come from Manifest."}]}
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
