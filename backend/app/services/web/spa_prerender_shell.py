"""Route-specific HTML shell metadata for crawlers and pre-hydration accessibility."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from app.services.web.agent_content import AGENT_PAGES, markdown_to_html


@dataclass(frozen=True)
class SpaRouteShell:
    path: str
    title: str
    description: str
    h1: str
    body_html: str
    canonical_path: str | None = None
    markdown_path: str | None = None


def _shell(
    path: str,
    *,
    title: str,
    description: str,
    h1: str,
    body: str,
    canonical_path: str | None = None,
) -> SpaRouteShell:
    return SpaRouteShell(
        path=path,
        title=title,
        description=description,
        h1=h1,
        body_html=body,
        canonical_path=canonical_path or path,
    )


ROUTE_SHELLS: dict[str, SpaRouteShell] = {
    "/login": _shell(
        "/login",
        title="Sign in to Manifest",
        description="Sign in to your Manifest workspace to continue building startup ideas and generated artifacts.",
        h1="Sign in to Manifest",
        body=(
            "<p>Use your email and password to access your ideas and documents.</p>"
            '<p>New here? <a href="/signup">Create an account</a>.</p>'
        ),
        canonical_path="/auth",
    ),
    "/signup": _shell(
        "/signup",
        title="Create your Manifest account",
        description="Create a Manifest account to save your startup ideas, generated documents, and collaboration workspace.",
        h1="Create your Manifest account",
        body=(
            "<p>Start a workspace to turn raw ideas into structured startup artifacts.</p>"
            '<p>Already have an account? <a href="/login">Sign in</a>.</p>'
        ),
        canonical_path="/auth",
    ),
    "/auth": _shell(
        "/auth",
        title="Sign in to Manifest",
        description="Sign in or create a Manifest account to access your startup workspace.",
        h1="Sign in to Manifest",
        body="<p>Access your ideas, pitch decks, and investor-ready documents.</p>",
    ),
    "/shorts": _shell(
        "/shorts",
        title="Pitch Reels — Discover startup ideas",
        description="Browse short pitch reels from published startup ideas on Manifest.",
        h1="Pitch Reels",
        body='<p>Discover founder pitch clips. Canonical route: <a href="/pitch-reels">/pitch-reels</a>.</p>',
        canonical_path="/pitch-reels",
    ),
    "/pitch-reels": _shell(
        "/pitch-reels",
        title="Pitch Reels — Discover startup ideas",
        description="Browse short pitch reels from published startup ideas on Manifest.",
        h1="Pitch Reels",
        body="<p>Watch founder pitch clips and explore published ideas.</p>",
    ),
}


def _agent_page_shells() -> dict[str, SpaRouteShell]:
    """Shells for public pages whose full text lives in ``agent_content``."""
    shells: dict[str, SpaRouteShell] = {}
    for page in AGENT_PAGES.values():
        shells[page.path] = SpaRouteShell(
            path=page.path,
            title=page.title,
            description=page.description,
            h1=page.h1,
            body_html=markdown_to_html(page.body_markdown),
            canonical_path=page.canonical_path or page.path,
            markdown_path=page.markdown_path,
        )
    home = shells["/"]
    shells["/home"] = SpaRouteShell(
        path="/home",
        title=home.title,
        description=home.description,
        h1=home.h1,
        body_html=home.body_html,
        canonical_path="/",
        markdown_path=home.markdown_path,
    )
    return shells


ROUTE_SHELLS.update(_agent_page_shells())


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    trimmed = path.split("?", 1)[0].split("#", 1)[0].strip()
    if not trimmed or trimmed == "/":
        return "/"
    return trimmed.rstrip("/") or "/"


def resolve_route_shell(path: str) -> SpaRouteShell | None:
    return ROUTE_SHELLS.get(normalize_path(path))


def apply_spa_shell(
    page_html: str, path: str, *, site_origin: str = "https://manifeststartup.com"
) -> str:
    """Inject route-specific title, meta, canonical, and static shell into index HTML."""
    shell = resolve_route_shell(path)
    if shell is None:
        return page_html

    safe_title = html.escape(shell.title)
    safe_description = html.escape(shell.description)
    canonical = f"{site_origin.rstrip('/')}{shell.canonical_path or shell.path}"
    safe_canonical = html.escape(canonical, quote=True)
    safe_h1 = html.escape(shell.h1)
    static_main = (
        f'<main id="manifest-static-shell" class="manifest-static-shell" data-server-shell="true">'
        f"<h1>{safe_h1}</h1>{shell.body_html}</main>"
    )

    updated = re.sub(
        r"<title>.*?</title>",
        lambda _m: f"<title>{safe_title}</title>",
        page_html,
        count=1,
        flags=re.I | re.S,
    )
    if re.search(r'<meta[^>]+name=["\']description["\']', updated, flags=re.I):
        updated = re.sub(
            r'<meta[^>]+name=["\']description["\'][^>]*>',
            lambda _m: f'<meta name="description" content="{safe_description}" />',
            updated,
            count=1,
            flags=re.I,
        )
    else:
        updated = updated.replace(
            "</head>",
            f'    <meta name="description" content="{safe_description}" />\n  </head>',
            1,
        )

    if re.search(r'<link[^>]+rel=["\']canonical["\']', updated, flags=re.I):
        updated = re.sub(
            r'<link[^>]+rel=["\']canonical["\'][^>]*>',
            lambda _m: f'<link rel="canonical" href="{safe_canonical}" />',
            updated,
            count=1,
            flags=re.I,
        )
    else:
        updated = updated.replace(
            "</head>",
            f'    <link rel="canonical" href="{safe_canonical}" />\n  </head>',
            1,
        )

    if shell.markdown_path:
        alternate = (
            f'<link rel="alternate" type="text/markdown" '
            f'href="{html.escape(shell.markdown_path, quote=True)}" />'
        )
        updated = re.sub(
            r'\s*<link[^>]+rel=["\']alternate["\'][^>]+text/markdown[^>]*>', "", updated, flags=re.I
        )
        updated = updated.replace("</head>", f"    {alternate}\n  </head>", 1)

    noscript_block = (
        '<noscript class="manifest-noscript-fallback">'
        f"<p><strong>{safe_h1}</strong></p>"
        f"<p>{safe_description}</p>"
        f'<p><a href="{html.escape(canonical)}">Open Manifest</a> — the full workspace needs JavaScript.</p>'
        "</noscript>"
    )
    if "manifest-noscript-fallback" in updated:
        updated = re.sub(
            r'<noscript[^>]*class="manifest-noscript-fallback"[^>]*>.*?</noscript>',
            lambda _m: noscript_block,
            updated,
            count=1,
            flags=re.I | re.S,
        )
    else:
        updated = re.sub(
            r"<noscript>.*?</noscript>",
            lambda _m: noscript_block,
            updated,
            count=1,
            flags=re.I | re.S,
        )

    if 'id="manifest-static-shell"' in updated:
        updated = re.sub(
            r'<main id="manifest-static-shell"[^>]*>.*?</main>',
            lambda _m: static_main,
            updated,
            count=1,
            flags=re.I | re.S,
        )
    else:
        updated = re.sub(
            r'(<div id="root"\s*>)',
            lambda m: f"{m.group(1)}\n      {static_main}\n    ",
            updated,
            count=1,
            flags=re.I,
        )

    return updated
