"""Public OpenAPI document for the API-key REST surface (``/api/v1``).

FastAPI's framework schema (``/internal/openapi.json`` outside production)
covers every internal and admin route, so it stays disabled in production.
This module builds a separate, public specification from the ``/api/v1``
router only, then layers on the security scheme, stable operation ids and
response schemas that the route handlers return as plain dicts.
"""

from __future__ import annotations

import copy
from functools import lru_cache
from typing import Any

from app.services.agent_content import SITE_ORIGIN
from fastapi.openapi.utils import get_openapi

_ERROR_RESPONSES = {
    "401": "Missing, malformed or invalid API key.",
    "403": "The key lacks a required scope, or the idea belongs to another user.",
    "429": "Per-minute, per-key or monthly request limit reached.",
    "500": "Unexpected server error.",
}

_COMPONENT_SCHEMAS: dict[str, Any] = {
    "Idea": {
        "type": "object",
        "description": "A startup idea owned by the API key's user.",
        "properties": {
            "object": {"type": "string", "enum": ["idea"]},
            "id": {"type": "string", "format": "uuid", "description": "Idea identifier."},
            "title": {"type": "string"},
            "description": {"type": ["string", "null"]},
            "created_at": {"type": ["string", "null"], "format": "date-time"},
            "updated_at": {"type": ["string", "null"], "format": "date-time"},
            "is_published": {"type": "boolean"},
            "has_business_model_canvas": {"type": "boolean"},
            "has_pitch_deck": {"type": "boolean"},
            "has_prd": {"type": "boolean"},
            "has_patent": {"type": "boolean"},
        },
        "required": ["id", "title"],
    },
    "IdeaList": {
        "type": "object",
        "description": "All ideas for the key's user, newest first. Not paginated.",
        "properties": {
            "object": {"type": "string", "enum": ["list"]},
            "data": {"type": "array", "items": {"$ref": "#/components/schemas/Idea"}},
        },
        "required": ["object", "data"],
    },
    "IdeaDeleted": {
        "type": "object",
        "properties": {"deleted": {"type": "boolean"}, "id": {"type": "string"}},
        "required": ["deleted", "id"],
    },
    "GenerationResult": {
        "type": "object",
        "properties": {
            "object": {"type": "string", "enum": ["generation_result"]},
            "idea_id": {"type": "string"},
            "status": {"type": "string", "enum": ["completed"]},
            "documents": {
                "type": "object",
                "description": (
                    "Per-document outcome keyed by business_model_canvas, pitch_deck, "
                    "product_requirements_document or provisional_patent."
                ),
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["generated", "failed"]},
                        "error": {"type": "string"},
                    },
                    "required": ["status"],
                },
            },
        },
        "required": ["object", "idea_id", "documents", "status"],
    },
    "Usage": {
        "type": "object",
        "description": "Usage statistics for the API client (fields may grow over time).",
        "properties": {"object": {"type": "string", "enum": ["usage"]}},
        "additionalProperties": True,
    },
    "ApiInfo": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string"},
            "status": {"type": "string"},
            "documentation": {"type": "string"},
        },
    },
    "Error": {
        "type": "object",
        "description": "Error envelope returned for every non-2xx /api/v1 response.",
        "properties": {
            "detail": {
                "type": "object",
                "properties": {
                    "error": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"},
                            "type": {
                                "type": "string",
                                "examples": [
                                    "authentication_error",
                                    "permission_error",
                                    "not_found_error",
                                    "rate_limit_error",
                                    "server_error",
                                ],
                            },
                            "code": {"type": "string", "examples": ["insufficient_scope"]},
                        },
                        "required": ["message", "type", "code"],
                    }
                },
                "required": ["error"],
            }
        },
        "required": ["detail"],
    },
}

# operationId -> (success status, response schema, required scope or None)
_OPERATIONS: dict[str, tuple[str, str, str | None]] = {
    "api_info": ("200", "ApiInfo", None),
    "list_ideas": ("200", "IdeaList", "ideas.read"),
    "create_idea": ("201", "Idea", "ideas.write"),
    "get_idea": ("200", "Idea", "ideas.read"),
    "update_idea": ("200", "Idea", "ideas.write"),
    "delete_idea": ("200", "IdeaDeleted", "ideas.write"),
    "generate_documents": ("200", "GenerationResult", "ideas.write"),
    "get_usage": ("200", "Usage", None),
}


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _json(schema_name: str) -> dict[str, Any]:
    return {"application/json": {"schema": _ref(schema_name)}}


@lru_cache(maxsize=1)
def _build() -> dict[str, Any]:
    from app.routes.api_v1_routes import router as api_v1_router

    spec = get_openapi(
        title="Manifest API",
        version="1.0.0",
        summary="Create startup ideas and generate business documents with AI.",
        description=(
            "Public REST API for Manifest. Authenticate with an API key sent as "
            "`Authorization: Bearer manifest_sk_...`. Keys carry scopes: `ideas.read` "
            "for reads and `ideas.write` for writes and generation (the coarse `read` and "
            "`write` scopes cover every `*.read` / `*.write` permission). Limits depend "
            f"on the API tier; see {SITE_ORIGIN}/pricing.md. Manifest is in development "
            "and the public site is a demo preview."
        ),
        routes=api_v1_router.routes,
        servers=[{"url": SITE_ORIGIN, "description": "Production"}],
        contact={"name": "Manifest", "url": f"{SITE_ORIGIN}/contact"},
    )
    spec["externalDocs"] = {"description": "API reference", "url": f"{SITE_ORIGIN}/docs/api"}
    components = spec.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    schemas.update(copy.deepcopy(_COMPONENT_SCHEMAS))
    components["securitySchemes"] = {
        "ApiKeyBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "manifest_sk_<64 hex characters>",
            "description": (
                "Manifest API key. Scopes granted to the key: ideas.read, ideas.write "
                "(or the coarse read / write)."
            ),
        }
    }

    seen_ids: set[str] = set()
    for _path, path_item in spec.get("paths", {}).items():
        for _method, operation in path_item.items():
            # Handler names are unique within the router; use them as stable ids.
            raw_id = operation.get("operationId", "")
            op_id = next((key for key in _OPERATIONS if raw_id.startswith(f"{key}_")), raw_id)
            if op_id in seen_ids:
                raise ValueError(f"duplicate operationId {op_id}")
            seen_ids.add(op_id)
            operation["operationId"] = op_id
            operation["tags"] = ["Ideas"] if "idea" in op_id else ["API"]

            # Auth travels in the security scheme, not as a header parameter.
            params = [
                p
                for p in operation.get("parameters", [])
                if not (p.get("in") == "header" and p.get("name", "").lower() == "authorization")
            ]
            if params:
                operation["parameters"] = params
            else:
                operation.pop("parameters", None)

            status, schema_name, scope = _OPERATIONS.get(op_id, ("200", "", None))
            responses: dict[str, Any] = {}
            success: dict[str, Any] = {"description": "Successful response."}
            if schema_name:
                success["content"] = _json(schema_name)
            responses[status] = success
            if "422" in operation.get("responses", {}):
                responses["422"] = operation["responses"]["422"]
            if op_id != "api_info":
                operation["security"] = [{"ApiKeyBearer": []}]
                for code, description in _ERROR_RESPONSES.items():
                    responses[code] = {"description": description, "content": _json("Error")}
                if "{idea_id}" in _path:
                    responses["404"] = {
                        "description": "No idea with this id.",
                        "content": _json("Error"),
                    }
                if scope:
                    operation["x-required-scopes"] = [scope]
                    operation["description"] = (
                        f"{operation.get('description', '').strip()}\n\nRequires scope `{scope}`."
                    ).strip()
            else:
                operation["security"] = []
            operation["responses"] = dict(sorted(responses.items()))
    return spec


def public_openapi_spec() -> dict[str, Any]:
    """Return a copy of the public OpenAPI document."""
    return copy.deepcopy(_build())
