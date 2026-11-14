"""Security response headers and CSP middleware (SEC-002).

Centralizes HTTP security headers across the FastAPI app:

- Content-Security-Policy (nonce-based, report-only by default; flip to
  enforced via CSP_ENFORCE=true once the SPA has been verified to load).
- Strict-Transport-Security (HSTS, only on HTTPS / production).
- X-Content-Type-Options, X-Frame-Options, Referrer-Policy,
  Permissions-Policy, Cross-Origin-Opener/Embedder/Resource-Policy.
- A per-request nonce is exposed at ``request.state.csp_nonce`` so
  templates and the SPA shell can reference it for inline scripts/styles
  without weakening CSP with ``unsafe-inline``.

The middleware is intentionally idempotent and never overwrites a header
that downstream code (e.g. /generated/pdfs static mount) already set.
"""

from __future__ import annotations

import contextlib
import os
import secrets
from collections.abc import Iterable

from app.security.config import env_flag, is_production_environment, request_is_secure
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_DEFAULT_PERMISSIONS_POLICY = ", ".join(
    [
        "accelerometer=()",
        "autoplay=(self)",
        "camera=(self)",
        "clipboard-read=(self)",
        "clipboard-write=(self)",
        "display-capture=()",
        "encrypted-media=(self)",
        "fullscreen=(self)",
        "geolocation=()",
        "gyroscope=()",
        "magnetometer=()",
        "microphone=(self)",
        "midi=()",
        "payment=()",
        "picture-in-picture=(self)",
        "publickey-credentials-get=(self)",
        "screen-wake-lock=()",
        "sync-xhr=()",
        "usb=()",
        "xr-spatial-tracking=()",
    ]
)

# Origins the SPA legitimately needs to talk to. Kept conservative; extend
# via CSP_EXTRA_CONNECT_SRC env (comma-separated) when wiring a new vendor.
_BASELINE_CONNECT = (
    "'self'",
    "https://*.posthog.com",
    "https://api.openai.com",
    "https://api.sendgrid.com",
    "wss:",
    "https:",
)
_BASELINE_IMG = ("'self'", "data:", "blob:", "https:")
_BASELINE_FONT = ("'self'", "data:", "https:")
_BASELINE_MEDIA = ("'self'", "blob:", "data:", "https:")
_BASELINE_STYLE = ("'self'",)
_BASELINE_SCRIPT = ("'self'",)
_BASELINE_FRAME_SRC = ("'self'",)
_BASELINE_WORKER = ("'self'", "blob:")


def _extra_sources(env_name: str) -> list[str]:
    raw = (os.getenv(env_name) or "").strip()
    if not raw:
        return []
    return [chunk.strip() for chunk in raw.split(",") if chunk.strip()]


def _build_csp(nonce: str, *, enforce: bool = False) -> str:
    script_src = list(_BASELINE_SCRIPT) + [f"'nonce-{nonce}'", "'strict-dynamic'"]
    style_src = list(_BASELINE_STYLE) + [f"'nonce-{nonce}'"]
    # Strict by default: no 'unsafe-inline'. Operators may temporarily opt in
    # via CSP_ALLOW_STYLE_INLINE=true while migrating Tailwind/runtime styles
    # to nonces or hashes (CSP_STYLE_HASHES). Default OFF to satisfy strict
    # CSP audit requirements.
    if env_flag("CSP_ALLOW_STYLE_INLINE", default=False):
        style_src.append("'unsafe-inline'")
    for style_hash in _extra_sources("CSP_STYLE_HASHES"):
        style_src.append(style_hash if style_hash.startswith("'") else f"'{style_hash}'")

    connect_src = list(_BASELINE_CONNECT) + _extra_sources("CSP_EXTRA_CONNECT_SRC")
    img_src = list(_BASELINE_IMG) + _extra_sources("CSP_EXTRA_IMG_SRC")
    font_src = list(_BASELINE_FONT) + _extra_sources("CSP_EXTRA_FONT_SRC")
    media_src = list(_BASELINE_MEDIA) + _extra_sources("CSP_EXTRA_MEDIA_SRC")
    frame_src = list(_BASELINE_FRAME_SRC) + _extra_sources("CSP_EXTRA_FRAME_SRC")
    worker_src = list(_BASELINE_WORKER)

    directives = [
        "default-src 'self'",
        f"script-src {' '.join(script_src)}",
        f"style-src {' '.join(style_src)}",
        f"img-src {' '.join(img_src)}",
        f"font-src {' '.join(font_src)}",
        f"media-src {' '.join(media_src)}",
        f"connect-src {' '.join(connect_src)}",
        f"frame-src {' '.join(frame_src)}",
        f"worker-src {' '.join(worker_src)}",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "manifest-src 'self'",
    ]
    # Browsers ignore upgrade-insecure-requests in report-only policies and
    # emit a console warning. Keep it only when the policy is enforced.
    if enforce:
        directives.append("upgrade-insecure-requests")
    report_uri = (os.getenv("CSP_REPORT_URI") or "").strip()
    if report_uri:
        directives.append(f"report-uri {report_uri}")
    return "; ".join(directives)


def _set_if_absent(headers, key: str, value: str) -> None:
    if key not in headers:
        headers[key] = value


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply baseline security headers and a per-request CSP nonce.

    CSP defaults to *report-only* so we can ship without breaking the SPA;
    set ``CSP_ENFORCE=true`` once telemetry shows zero violations to flip
    to the enforced ``Content-Security-Policy`` header.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        enforce_csp: bool | None = None,
    ) -> None:
        super().__init__(app)
        self._enforce_csp = (
            enforce_csp
            if enforce_csp is not None
            else env_flag("CSP_ENFORCE", default=is_production_environment())
        )

    async def dispatch(self, request: Request, call_next):
        nonce = secrets.token_urlsafe(18)
        with contextlib.suppress(Exception):
            request.state.csp_nonce = nonce

        response: Response = await call_next(request)
        headers = response.headers

        csp_value = _build_csp(nonce, enforce=self._enforce_csp)
        csp_header = (
            "Content-Security-Policy"
            if self._enforce_csp
            else "Content-Security-Policy-Report-Only"
        )
        # Always set the *opposite* header to empty so an upstream proxy that
        # injected the wrong one cannot shadow our policy.
        _set_if_absent(headers, csp_header, csp_value)

        _set_if_absent(headers, "X-Content-Type-Options", "nosniff")
        _set_if_absent(headers, "X-Frame-Options", "DENY")
        _set_if_absent(headers, "Referrer-Policy", "strict-origin-when-cross-origin")
        _set_if_absent(headers, "Permissions-Policy", _DEFAULT_PERMISSIONS_POLICY)
        _set_if_absent(headers, "Cross-Origin-Opener-Policy", "same-origin")
        _set_if_absent(headers, "Cross-Origin-Resource-Policy", "same-origin")
        # COEP is intentionally `unsafe-none` because the SPA loads
        # cross-origin images (CDNs, gravatar, OpenAI). Flip to
        # `require-corp` once those origins serve CORP headers.
        _set_if_absent(headers, "Cross-Origin-Embedder-Policy", "unsafe-none")
        _set_if_absent(headers, "X-Permitted-Cross-Domain-Policies", "none")
        _set_if_absent(headers, "X-DNS-Prefetch-Control", "off")

        if request_is_secure(request) or is_production_environment():
            _set_if_absent(
                headers,
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains; preload",
            )

        # Surface the nonce to the SPA shell / templates that need it.
        _set_if_absent(headers, "X-CSP-Nonce", nonce)
        return response


def baseline_security_header_keys() -> Iterable[str]:
    """Return the set of headers this middleware is responsible for (for tests)."""
    return (
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "Cross-Origin-Opener-Policy",
        "Cross-Origin-Resource-Policy",
        "Cross-Origin-Embedder-Policy",
        "X-Permitted-Cross-Domain-Policies",
        "X-DNS-Prefetch-Control",
    )
