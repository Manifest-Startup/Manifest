"""SPA fallback: serve the React shell for real client routes, 404 everything else.

The React router (``frontend/src/App.tsx`` and ``features/ios/AppIOS.tsx``)
owns the client routes. Only paths that match one of those routes get the
HTML shell with HTTP 200; any other path that is not a file in the build
directory gets a real 404 with a small HTML or Markdown body, so agents and
crawlers do not mistake every URL for an existing page (soft 404).

``backend/tests/test_spa_fallback.py`` parses both router files and fails
when a route is added there but not here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from app.services.web.agent_content import (
    SITE_ORIGIN,
    get_agent_page,
    markdown_to_html,
    not_found_markdown,
)
from app.services.web.spa_prerender_shell import apply_spa_shell, normalize_path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

# Exact client routes (keep in sync with App.tsx / AppIOS.tsx).
SPA_EXACT_ROUTES: frozenset[str] = frozenset(
    {
        "/",
        "/home",
        "/research",
        "/feedback/survey",
        "/ideas",
        "/ideas/qualify",
        "/account",
        "/account/billing",
        "/admin/cost",
        "/login",
        "/signup",
        "/auth",
        "/auth/forgot-password",
        "/auth/reset-password",
        "/learn-more",
        "/messages",
        "/pitch-reels",
        "/shorts",
        "/discover",
        "/pitch-shorts",
        "/portfolio",
        "/docs",
        "/docs/guide",
        "/docs/api",
        "/legal/terms",
        "/legal/privacy",
        "/about",
        "/contact",
        "/privacy",
        "/developers",
    }
)

# Parameterised client routes, as React Router patterns.
SPA_PATTERN_ROUTES: tuple[str, ...] = (
    "/ideas/:idea_id",
    "/ideas/:idea_id/:ideaAspect",
    "/messages/:conversationId",
)

_SEGMENT = r"[^/]+"
_PATTERN_RES = tuple(
    re.compile("^" + re.sub(r":[A-Za-z_]+", _SEGMENT, pattern) + "$")
    for pattern in SPA_PATTERN_ROUTES
)

# Prefixes owned by backend routers; never answered with the SPA shell.
API_PATH_PREFIXES = ("graphql", "socket.io", "ping", "api")

DISCOVERY_LINK_HEADER = ", ".join(
    [
        '</index.md>; rel="alternate"; type="text/markdown"',
        '</llms.txt>; rel="describedby"; type="text/plain"',
        '</agents.md>; rel="help"; type="text/markdown"',
        '</openapi.json>; rel="service-desc"; type="application/vnd.oai.openapi+json"',
        '</docs/api>; rel="service-doc"; type="text/html"',
        '</.well-known/api-catalog>; rel="api-catalog"',
        '</.well-known/ard.json>; rel="ard"; type="application/json"',
        '</sitemap.xml>; rel="sitemap"; type="application/xml"',
        '</.well-known/ard.json>; rel="ard"; type="application/json"',
    ]
)


def is_spa_route(path: str) -> bool:
    normalized = normalize_path(path)
    if normalized in SPA_EXACT_ROUTES:
        return True
    return any(pattern.match(normalized) for pattern in _PATTERN_RES)


def _media_ranges(accept: str) -> list[tuple[str, float]]:
    ranges: list[tuple[str, float]] = []
    for part in accept.split(","):
        pieces = [p.strip() for p in part.split(";")]
        media = pieces[0].lower()
        if not media:
            continue
        q = 1.0
        for param in pieces[1:]:
            if param.lower().startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 0.0
        ranges.append((media, q))
    return ranges


def prefers_markdown(accept: str | None) -> bool:
    """True when the client explicitly asks for Markdown at least as much as HTML."""
    if not accept:
        return False
    ranges = _media_ranges(accept)
    markdown_q = max(
        (q for media, q in ranges if media in {"text/markdown", "text/x-markdown"}), default=0.0
    )
    if markdown_q <= 0:
        return False
    html_q = max(
        (q for media, q in ranges if media in {"text/html", "application/xhtml+xml"}),
        default=0.0,
    )
    return markdown_q >= html_q


def markdown_response(
    body: str,
    *,
    status_code: int = 200,
    canonical_path: str | None = None,
    vary_accept: bool = False,
) -> Response:
    headers: dict[str, str] = {}
    if body.lstrip().startswith("---"):
        metadata_body = body
    else:
        heading = next(
            (line.lstrip("# ").strip() for line in body.splitlines() if line.startswith("# ")),
            "Manifest",
        )
        metadata = ["---", f'title: "{heading.replace(chr(34), chr(92) + chr(34))}"']
        if canonical_path:
            metadata.append(f'canonical: "{SITE_ORIGIN}{canonical_path}"')
        metadata.extend(["---", ""])
        metadata_body = "\n".join(metadata) + body.lstrip()
    if canonical_path:
        headers["Link"] = f'<{SITE_ORIGIN}{canonical_path}>; rel="canonical"'
    if vary_accept:
        headers["Vary"] = "Accept"
    return Response(
        content=metadata_body,
        status_code=status_code,
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )


def not_found_response(path: str, accept: str | None) -> Response:
    markdown = not_found_markdown(path)
    if prefers_markdown(accept):
        return markdown_response(markdown, status_code=404, vary_accept=True)
    page = (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />'
        '<meta name="robots" content="noindex" />'
        "<title>Page not found · Manifest</title>"
        '<link rel="alternate" type="text/markdown" href="/llms.txt" />'
        "<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;"
        "padding:0 1rem;line-height:1.6;color:#0f172a;background:#fff}"
        "code{background:#f1f5f9;padding:0 .25rem;border-radius:4px}a{color:#2563eb}</style>"
        f"</head><body><main>{markdown_to_html(markdown)}</main></body></html>"
    )
    return HTMLResponse(page, status_code=404, headers={"Vary": "Accept"})


def _safe_build_file(build_dir: Path, full_path: str) -> Path | None:
    if not full_path:
        return None
    try:
        candidate = (build_dir / full_path).resolve()
        candidate.relative_to(build_dir.resolve())
    except (ValueError, OSError):
        return None
    return candidate if candidate.is_file() else None


def register_spa_fallback(app: FastAPI, build_dir: Path, index_html: Callable[[], str]) -> None:
    """Register the catch-all GET route. Call after every other route is added."""

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_react_app(full_path: str, request: Request) -> Response:
        if full_path.startswith(API_PATH_PREFIXES):
            raise HTTPException(status_code=404, detail="Not found")

        file_path = _safe_build_file(build_dir, full_path)
        if file_path is not None:
            return FileResponse(file_path)

        path = normalize_path(f"/{full_path}")
        accept = request.headers.get("accept")
        if not is_spa_route(path):
            return not_found_response(path, accept)

        if path == "/home":
            path = "/"
        page = get_agent_page(path)
        if page is not None and prefers_markdown(accept):
            return markdown_response(
                page.markdown,
                canonical_path=page.canonical_path or page.path,
                vary_accept=True,
            )

        headers = {"Vary": "Accept"}
        if path == "/":
            headers["Link"] = DISCOVERY_LINK_HEADER
        elif page is not None:
            headers["Link"] = f'<{page.markdown_path}>; rel="alternate"; type="text/markdown"'
        return HTMLResponse(apply_spa_shell(index_html(), path), headers=headers)
