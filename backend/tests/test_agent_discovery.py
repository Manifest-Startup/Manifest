"""Agent-readiness surface: discovery documents, Markdown twins, OpenAPI, SPA 404s."""

from __future__ import annotations

import json
import re
from pathlib import Path

import app.main as main_module
import pytest
from app.main import fastapi_app
from app.services.agent_content import AGENT_PAGES, markdown_to_html
from app.services.spa_fallback import is_spa_route, prefers_markdown, register_spa_fallback
from fastapi import FastAPI
from fastapi.testclient import TestClient

def _markdown_body(text: str) -> str:
    """Strip the YAML front matter (title/canonical) that agent pages start with."""
    if text.startswith("---\n"):
        _, _, rest = text[4:].partition("\n---\n")
        return rest
    return text


REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_HTML = (REPO_ROOT / "frontend" / "public" / "index.html").read_text(encoding="utf-8")
ROUTER_FILES = (
    REPO_ROOT / "frontend" / "src" / "App.tsx",
    REPO_ROOT / "frontend" / "src" / "features" / "ios" / "AppIOS.tsx",
)
MARKDOWN = {"Accept": "text/markdown"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(fastapi_app)


@pytest.fixture()
def spa_client(tmp_path: Path) -> TestClient:
    """A tiny app wired exactly like production's SPA fallback."""
    (tmp_path / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (tmp_path / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    app = FastAPI()
    register_spa_fallback(app, tmp_path, lambda: INDEX_HTML)
    return TestClient(app)


def _visible_text(page_html: str) -> str:
    body = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", page_html, flags=re.S | re.I)
    body = re.sub(r"<head>.*?</head>", " ", body, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()


# ---------------------------------------------------------------- well-known


@pytest.mark.parametrize("path", ["/.well-known/ard.json", "/.well-known/ai-catalog.json"])
def test_agentic_resource_catalogs_are_valid(client: TestClient, path: str):
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.headers["access-control-allow-origin"] == "*"
    entries = resp.json()["entries"]
    assert entries
    for entry in entries:
        assert re.match(r"^urn:air:manifeststartup\.com:[\w-]+:[\w-]+$", entry["identifier"])
        assert entry["displayName"]
        assert "/" in entry["type"]
        assert ("url" in entry) != ("data" in entry)
    if path.endswith("ai-catalog.json"):
        assert resp.json()["specVersion"] == "1.0"


def test_api_catalog_is_rfc9727_linkset(client: TestClient):
    resp = client.get("/.well-known/api-catalog")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/linkset+json")
    assert "rfc9727" in resp.headers["content-type"]
    linkset = resp.json()["linkset"]
    hrefs = {
        link["href"]
        for item in linkset
        for rel in item.values()
        if isinstance(rel, list)
        for link in rel
    }
    assert "https://manifeststartup.com/openapi.json" in hrefs
    assert any("item" in item for item in linkset)

    head = client.head("/.well-known/api-catalog")
    assert head.status_code == 200
    assert 'rel="api-catalog"' in head.headers["link"]


# ------------------------------------------------------------------- openapi


def test_public_openapi_describes_only_api_v1(client: TestClient):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["openapi"].startswith("3.")
    assert spec["paths"]
    assert all(path.startswith("/api/v1") for path in spec["paths"])

    from app.routes.api_v1_routes import router as api_v1_router

    route_ops = {
        (route.path, method.lower())
        for route in api_v1_router.routes
        for method in getattr(route, "methods", set())
    }
    assert route_ops
    spec_ops = {(path, method) for path, item in spec["paths"].items() for method in item}
    assert spec_ops == route_ops

    op_ids = [op["operationId"] for item in spec["paths"].values() for op in item.values()]
    assert len(op_ids) == len(set(op_ids))
    assert "ApiKeyBearer" in spec["components"]["securitySchemes"]
    for item in spec["paths"].values():
        for op in item.values():
            assert op.get("description") or op.get("summary")
            assert all(p["name"].lower() != "authorization" for p in op.get("parameters", []))
            success = next(code for code in op["responses"] if code.startswith("2"))
            assert "content" in op["responses"][success]


def test_framework_schema_moves_off_public_openapi_path_outside_production():
    previous = main_module._IS_NON_PROD
    try:
        main_module._IS_NON_PROD = True
        kwargs = main_module._fastapi_docs_kwargs()
    finally:
        main_module._IS_NON_PROD = previous
    assert kwargs["openapi_url"] == "/internal/openapi.json"


# ------------------------------------------------------------------ markdown


@pytest.mark.parametrize(
    "path",
    [
        "/agents.md",
        "/AGENTS.md",
        "/pricing.md",
        "/index.md",
        "/about.md",
        "/contact.md",
        "/privacy.md",
        "/docs/api.md",
    ],
)
def test_markdown_documents_start_with_heading(client: TestClient, path: str):
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert _markdown_body(resp.text).startswith("# ")
    assert 'rel="canonical"' in resp.headers["link"]


def test_agent_guide_has_when_to_use_section(client: TestClient):
    body = client.get("/agents.md").text
    assert "## When to use Manifest" in body
    assert "## When not to use Manifest" in body
    assert "/openapi.json" in body


def test_pricing_md_matches_enforced_tiers(client: TestClient):
    from app.services.api_key_service import BillingTier

    body = client.get("/pricing.md").text
    for tier in (BillingTier.FREE, BillingTier.STARTER, BillingTier.PRO):
        assert f"{BillingTier.LIMITS[tier]['requests_per_month']:,}" in body


@pytest.mark.parametrize(
    ("accept", "expected"),
    [
        ("text/markdown", True),
        ("text/markdown, text/html;q=0.9", True),
        ("text/html,application/xhtml+xml,*/*;q=0.8", False),
        ("text/html, text/markdown;q=0.5", False),
        ("*/*", False),
        (None, False),
        ("text/markdown;q=0", False),
    ],
)
def test_prefers_markdown(accept, expected):
    assert prefers_markdown(accept) is expected


def test_markdown_to_html_renders_lists_links_and_code():
    rendered = markdown_to_html("## Hi\n\n- a [link](/x) and `<b>`\n  continued\n\n```\n<raw>\n```")
    assert rendered.startswith(
        '<h2>Hi</h2><ul><li>a <a href="/x">link</a> and <code>&lt;b&gt;</code> continued</li></ul>'
    )
    assert "<pre><code>&lt;raw&gt;</code></pre>" in rendered


# --------------------------------------------------------------- SPA fallback


def test_homepage_html_has_prerendered_content_and_discovery_headers(spa_client: TestClient):
    resp = spa_client.get("/", headers={"Accept": "text/html"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert resp.headers["vary"] == "Accept"
    link = resp.headers["link"]
    for target in (
        "/openapi.json",
        "/.well-known/api-catalog",
        "/llms.txt",
        "/index.md",
        "/sitemap.xml",
    ):
        assert target in link
    assert len(_visible_text(resp.text)) >= 500
    assert 'href="/docs/api"' in resp.text
    assert 'rel="alternate" type="text/markdown" href="/index.md"' in resp.text
    assert resp.text.count("<h1") == 1


def test_homepage_negotiates_markdown(spa_client: TestClient):
    resp = spa_client.get("/", headers=MARKDOWN)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert resp.headers["vary"] == "Accept"
    assert _markdown_body(resp.text).startswith("# ")


@pytest.mark.parametrize(
    "path", ["/about", "/contact", "/privacy", "/legal/privacy", "/docs/api", "/developers"]
)
def test_trust_and_docs_pages_have_text_without_javascript(spa_client: TestClient, path: str):
    resp = spa_client.get(path)
    assert resp.status_code == 200
    assert len(_visible_text(resp.text)) >= 500


@pytest.mark.parametrize(
    "path",
    [
        "/ideas",
        "/ideas/abc",
        "/ideas/abc/pitch-deck",
        "/messages/c1",
        "/pitch-reels",
        "/auth/reset-password",
        "/home/",
    ],
)
def test_client_routes_still_return_the_shell(spa_client: TestClient, path: str):
    resp = spa_client.get(path)
    assert resp.status_code == 200
    assert '<div id="root">' in resp.text


@pytest.mark.parametrize(
    "path",
    [
        "/definitely-not-a-page",
        "/.well-known/http-message-signatures-directory",
        "/ideas/a/b/c",
        "/auth.md",
        "/wp-login.php",
    ],
)
def test_unknown_paths_are_real_404s(spa_client: TestClient, path: str):
    resp = spa_client.get(path)
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("text/html")
    assert '<div id="root">' not in resp.text
    assert 'href="/llms.txt"' in resp.text

    md = spa_client.get(path, headers=MARKDOWN)
    assert md.status_code == 404
    assert md.headers["content-type"].startswith("text/markdown")
    assert _markdown_body(md.text).startswith("# Page not found")


def test_build_files_and_api_prefixes(spa_client: TestClient):
    assert spa_client.get("/robots.txt").status_code == 200
    assert spa_client.get("/api/not-a-route").status_code == 404
    assert spa_client.get("/api/not-a-route").headers["content-type"].startswith("application/json")
    assert spa_client.get("/..%2F..%2Fetc%2Fpasswd").status_code == 404


def _router_paths() -> set[str]:
    paths: set[str] = set()
    for router_file in ROUTER_FILES:
        source = router_file.read_text(encoding="utf-8")
        paths.update(re.findall(r'<Route\s+path="([^"]+)"', source))
    paths.discard("*")
    return paths


def test_every_react_route_is_served_by_the_backend():
    paths = _router_paths()
    assert "/" in paths and "/ideas/:idea_id" in paths
    missing = [p for p in sorted(paths) if not is_spa_route(re.sub(r":\w+", "sample", p))]
    assert not missing, f"Add these React routes to spa_fallback.SPA_*_ROUTES: {missing}"


def test_every_agent_page_is_a_client_route():
    for path in AGENT_PAGES:
        assert is_spa_route(path), path


def test_discovery_json_is_serializable():
    from app.routes.agent_discovery_routes import ai_catalog, api_catalog, ard_catalog

    for doc in (ard_catalog(), ai_catalog(), api_catalog()):
        json.dumps(doc)


EDGE_SERVED_PATHS = {"/mcp", "/docs/mcp"}  # deploy/cloudflare/src/index.mjs routes these


def test_llms_txt_links_resolve_to_real_resources(client: TestClient):
    llms = (REPO_ROOT / "frontend" / "public" / "llms.txt").read_text(encoding="utf-8")
    assert llms.startswith("# ")
    links = re.findall(r"\]\((https://manifeststartup\.com[^)]*)\)", llms)
    assert len(links) >= 10
    public_dir = REPO_ROOT / "frontend" / "public"
    for url in links:
        path = url.removeprefix("https://manifeststartup.com") or "/"
        if (public_dir / path.lstrip("/")).is_file() or is_spa_route(path):
            continue
        if path in EDGE_SERVED_PATHS:  # answered by the Cloudflare Worker, never the backend
            continue
        assert client.get(path).status_code == 200, url
