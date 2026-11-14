"""Machine-readable discovery documents for AI agents and crawlers.

* ``/.well-known/ard.json`` and ``/.well-known/ai-catalog.json`` — agentic
  resource catalogs (ARD / AI Catalog) listing the public REST API and the
  agent guide.
* ``/.well-known/api-catalog`` — RFC 9727 API catalog (linkset).
* ``/openapi.json`` — public OpenAPI document for ``/api/v1`` only.
* ``/agents.md``, ``/pricing.md`` and ``.md`` twins of the public pages.

Only real, publicly reachable resources may be listed here.
"""

from __future__ import annotations

from typing import Any

from app.services.web.agent_content import (
    AGENTS_MARKDOWN,
    MARKDOWN_TWINS,
    SITE_ORIGIN,
    pricing_markdown,
)
from app.services.web.public_openapi import public_openapi_spec
from app.services.web.spa_fallback import markdown_response
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter(tags=["Agent discovery"], include_in_schema=False)

OPENAPI_MEDIA_TYPE = "application/vnd.oai.openapi+json;version=3.1"
API_CATALOG_MEDIA_TYPE = (
    'application/linkset+json; profile="https://www.rfc-editor.org/info/rfc9727"'
)
_PUBLIC_JSON_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "public, max-age=3600",
}


def _catalog_entries() -> list[dict[str, Any]]:
    return [
        {
            "identifier": "urn:air:manifeststartup.com:api:rest-v1",
            "displayName": "Manifest REST API",
            "type": OPENAPI_MEDIA_TYPE,
            "url": f"{SITE_ORIGIN}/openapi.json",
            "description": (
                "Create and manage startup ideas and generate a business model canvas, "
                "pitch deck, product requirements document or provisional patent draft "
                "for them. Requires a Manifest API key (Bearer manifest_sk_...)."
            ),
            "capabilities": [
                "list_ideas",
                "create_idea",
                "get_idea",
                "update_idea",
                "delete_idea",
                "generate_documents",
                "get_usage",
            ],
            "representativeQueries": [
                "turn my startup idea into a pitch deck",
                "generate a business model canvas for an idea",
                "write a product requirements document for my app idea",
                "draft a provisional patent for my invention idea",
            ],
        },
        {
            "identifier": "urn:air:manifeststartup.com:docs:agent-guide",
            "displayName": "Manifest agent guide",
            "type": "text/markdown",
            "url": f"{SITE_ORIGIN}/agents.md",
            "description": "When AI agents should use Manifest and how to call its API.",
            "representativeQueries": [
                "which tool can turn a startup idea into investor documents",
                "how do I call the Manifest API",
            ],
        },
        {
            "identifier": "urn:air:manifeststartup.com:skills:manifest-api",
            "displayName": "Manifest API integration skill",
            "type": "text/markdown",
            "url": f"{SITE_ORIGIN}/skills/manifest-api/SKILL.md",
            "description": "Guidance for agents that use Manifest's API-key REST API.",
            "representativeQueries": [
                "how should an agent manage startup ideas with Manifest",
                "how do I generate documents through the Manifest API",
            ],
        },
        {
            "identifier": "urn:air:manifeststartup.com:mcp:api",
            "displayName": "Manifest MCP server",
            "type": "application/mcp-server-card+json",
            "url": f"{SITE_ORIGIN}/.well-known/mcp/server-card.json",
            "description": "Streamable HTTP tools for authenticated idea and document operations.",
            "capabilities": [
                "list_ideas",
                "create_idea",
                "get_idea",
                "update_idea",
                "delete_idea",
                "generate_documents",
                "get_usage",
            ],
            "representativeQueries": [
                "manage my startup ideas in Manifest",
                "generate a pitch deck for my Manifest idea",
            ],
        },
        {
            "identifier": "urn:air:manifeststartup.com:mcp:docs",
            "displayName": "Manifest documentation MCP server",
            "type": "application/mcp-server-card+json",
            "url": f"{SITE_ORIGIN}/.well-known/mcp/docs-server-card.json",
            "description": "Read-only Streamable HTTP tools for Manifest API and product documentation.",
            "capabilities": ["list_manifest_documents", "read_manifest_document"],
            "representativeQueries": [
                "find Manifest API authentication instructions",
                "read the Manifest API plans and limits",
            ],
        },
    ]


def ard_catalog() -> dict[str, Any]:
    return {"entries": _catalog_entries()}


def ai_catalog() -> dict[str, Any]:
    return {"specVersion": "1.0", "entries": _catalog_entries()}


def api_catalog() -> dict[str, Any]:
    return {
        "linkset": [
            {
                "anchor": f"{SITE_ORIGIN}/.well-known/api-catalog",
                "item": [{"href": f"{SITE_ORIGIN}/api/v1/"}],
            },
            {
                "anchor": f"{SITE_ORIGIN}/api/v1/",
                "service-desc": [
                    {"href": f"{SITE_ORIGIN}/openapi.json", "type": OPENAPI_MEDIA_TYPE}
                ],
                "service-doc": [{"href": f"{SITE_ORIGIN}/docs/api", "type": "text/html"}],
                "service-meta": [{"href": f"{SITE_ORIGIN}/agents.md", "type": "text/markdown"}],
                "status": [{"href": f"{SITE_ORIGIN}/api/v1/", "type": "application/json"}],
            },
        ]
    }


@router.get("/.well-known/ard.json")
async def well_known_ard() -> JSONResponse:
    return JSONResponse(ard_catalog(), headers=_PUBLIC_JSON_HEADERS)


@router.get("/.well-known/ai-catalog.json")
async def well_known_ai_catalog() -> JSONResponse:
    return JSONResponse(ai_catalog(), headers=_PUBLIC_JSON_HEADERS)


@router.get("/.well-known/agent-skills/index.json")
async def well_known_agent_skills() -> JSONResponse:
    # No installable skills package is published yet. This standards-shaped
    # empty index states that honestly and provides the discovery endpoint.
    return JSONResponse({"skills": []}, headers=_PUBLIC_JSON_HEADERS)


@router.api_route("/.well-known/api-catalog", methods=["GET", "HEAD"])
async def well_known_api_catalog(request: Request) -> Response:
    headers = {
        **_PUBLIC_JSON_HEADERS,
        "Link": f'<{SITE_ORIGIN}/.well-known/api-catalog>; rel="api-catalog"',
    }
    if request.method == "HEAD":
        return Response(status_code=200, media_type=API_CATALOG_MEDIA_TYPE, headers=headers)
    return JSONResponse(api_catalog(), media_type=API_CATALOG_MEDIA_TYPE, headers=headers)


@router.get("/openapi.json")
async def public_openapi() -> JSONResponse:
    return JSONResponse(public_openapi_spec(), headers=_PUBLIC_JSON_HEADERS)


@router.get("/agents.md")
@router.get("/AGENTS.md")
async def agents_markdown() -> Response:
    return markdown_response(AGENTS_MARKDOWN, canonical_path="/agents.md")


@router.get("/pricing.md")
async def pricing_md() -> Response:
    return markdown_response(pricing_markdown(), canonical_path="/pricing.md")


def _register_markdown_twin(md_path: str) -> None:
    page = MARKDOWN_TWINS[md_path]
    canonical = page.canonical_path or page.path

    async def _twin() -> Response:
        return markdown_response(page.markdown, canonical_path=canonical)

    router.add_api_route(md_path, _twin, methods=["GET"], name=f"markdown_twin:{md_path}")


for _md_path in sorted(MARKDOWN_TWINS):
    _register_markdown_twin(_md_path)
