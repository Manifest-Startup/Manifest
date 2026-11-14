"""
Manifest Public API v1 Routes

REST API endpoints for programmatic access to Manifest features.
Similar to OpenAI's API structure.
"""

import time
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypedDict

from app.db.database import db_client
from app.managers.manifest_manager import ManifestManager
from app.services.documents.provisional_patent import ProvisionalPatent
from app.services.identity.api_keys import api_key_service, api_usage_service
from app.utils.logger import logger
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["API v1"])


class AuthInfo(TypedDict):
    key_id: str
    client_id: str
    user_id: str
    tier: str
    limits: dict[str, int]
    scopes: list[str]


def _api_error(status_code: int, message: str, error_type: str, code: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "message": message,
                "type": error_type,
                "code": code,
            }
        },
    )


def _to_single_record(data: Any) -> dict:
    if isinstance(data, list):
        return data[0] if data else {}
    return data or {}


def _record_usage(
    auth_info: AuthInfo,
    endpoint: str,
    response_code: int,
    start_time: float,
    *,
    tokens_used: int = 0,
) -> None:
    """Record API usage without affecting endpoint response flow."""
    try:
        latency_ms = int((time.time() - start_time) * 1000)
        api_usage_service.record_usage(
            client_id=auth_info["client_id"],
            key_id=auth_info["key_id"],
            endpoint=endpoint,
            response_code=response_code,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
        )
    except Exception as usage_error:
        logger.warning(f"Failed to record API usage for {endpoint}: {usage_error}")


def _get_user_idea_or_raise(idea_id: str, auth_info: AuthInfo) -> dict:
    existing_result = db_client.table("ideas").select("*").eq("idea_id", idea_id).single().execute()
    idea = existing_result.data

    if not idea:
        raise _api_error(
            status_code=404,
            message=f"Idea '{idea_id}' not found",
            error_type="not_found_error",
            code="idea_not_found",
        )

    if idea.get("user_id") != auth_info["user_id"]:
        raise _api_error(
            status_code=403,
            message="You don't have access to this idea",
            error_type="permission_error",
            code="forbidden",
        )

    return idea


class ApiKeyAuth:
    """Dependency for API key authentication."""

    async def __call__(self, authorization: str | None = Header(None)) -> AuthInfo:
        if not authorization:
            raise _api_error(
                status_code=401,
                message="Missing API key. Include 'Authorization: Bearer manifest_sk_...' header.",
                error_type="authentication_error",
                code="missing_api_key",
            )

        if not authorization.startswith("Bearer "):
            raise _api_error(
                status_code=401,
                message="Invalid authorization format. Use 'Bearer manifest_sk_...'",
                error_type="authentication_error",
                code="invalid_format",
            )

        api_key = authorization[7:]
        auth_info = api_key_service.validate_api_key(api_key)
        if not auth_info:
            raise _api_error(
                status_code=401,
                message="Invalid API key provided.",
                error_type="authentication_error",
                code="invalid_api_key",
            )

        if not api_usage_service.check_rate_limit(auth_info["client_id"], auth_info["tier"]):
            raise _api_error(
                status_code=429,
                message=(
                    f"Rate limit exceeded. Your tier allows "
                    f"{auth_info['limits']['rate_limit_per_minute']} requests per minute."
                ),
                error_type="rate_limit_error",
                code="rate_limit_exceeded",
            )

        # Per-key ceiling — defends against a single leaked key bursting
        # within an otherwise-quiet client.
        if not api_usage_service.check_per_key_rate_limit(auth_info["key_id"]):
            raise _api_error(
                status_code=429,
                message="Per-key rate limit exceeded.",
                error_type="rate_limit_error",
                code="key_rate_limit_exceeded",
            )

        if not api_usage_service.check_monthly_limit(auth_info["client_id"], auth_info["tier"]):
            raise _api_error(
                status_code=429,
                message=(
                    f"Monthly request limit exceeded. Your tier allows "
                    f"{auth_info['limits']['requests_per_month']} requests per month."
                ),
                error_type="rate_limit_error",
                code="monthly_limit_exceeded",
            )

        return auth_info


api_key_auth = ApiKeyAuth()


def require_scope(*required: str) -> Callable:
    """Return a FastAPI dependency that 403s when the calling key lacks
    every one of the required scopes. Wildcard ``*`` grants everything.
    """

    async def _dep(auth_info: AuthInfo = Depends(api_key_auth)) -> AuthInfo:
        granted = set(auth_info.get("scopes") or [])
        if "*" in granted:
            return auth_info

        def _satisfies(req: str) -> bool:
            # Direct grant.
            if req in granted:
                return True
            # Coarse-grained legacy aliases: "read" implies *.read,
            # "write" implies *.write. This preserves backwards compat
            # while still rejecting reads-only keys from writing.
            if "." in req:
                _, verb = req.rsplit(".", 1)
                if verb in granted:
                    return True
            return False

        missing = [s for s in required if not _satisfies(s)]
        if missing:
            raise _api_error(
                status_code=403,
                message=f"API key missing required scope(s): {', '.join(missing)}",
                error_type="permission_error",
                code="insufficient_scope",
            )
        return auth_info

    return _dep


class IdeaCreate(BaseModel):
    title: str = Field(..., description="Title of the idea", min_length=1, max_length=500)
    description: str | None = Field(None, description="Description of the idea")


class IdeaUpdate(BaseModel):
    title: str | None = Field(None, description="New title for the idea")
    description: str | None = Field(None, description="New description for the idea")


class DocumentGenerate(BaseModel):
    document_types: list[str] = Field(
        default=["business_model_canvas"],
        description="Types of documents to generate: business_model_canvas, pitch_deck, prd, patent",
    )


def format_idea(idea: dict) -> dict:
    """Format an idea for API response."""
    return {
        "id": idea.get("idea_id"),
        "title": idea.get("title"),
        "description": idea.get("description"),
        "created_at": idea.get("created_at"),
        "updated_at": idea.get("updated_at"),
        "is_published": idea.get("is_published", False),
        "has_business_model_canvas": idea.get("business_model_canvas") is not None,
        "has_pitch_deck": idea.get("pitch_deck") is not None,
        "has_prd": idea.get("product_requirements_document") is not None,
        "has_patent": idea.get("provisional_patent") is not None,
    }


@router.get("/")
async def api_info():
    """Get API information and status."""
    return {
        "name": "Manifest API",
        "version": "1.0.0",
        "status": "operational",
        "documentation": "/api/docs",
    }


@router.get("/ideas")
async def list_ideas(auth_info: AuthInfo = Depends(require_scope("ideas.read"))):
    """List all ideas for the authenticated user."""
    start_time = time.time()
    try:
        result = (
            db_client.table("ideas")
            .select("*")
            .eq("user_id", auth_info["user_id"])
            .order("created_at", desc=True)
            .execute()
        )
        ideas = result.data or []

        _record_usage(auth_info, endpoint="GET /ideas", response_code=200, start_time=start_time)
        return {"object": "list", "data": [format_idea(idea) for idea in ideas]}
    except Exception as e:
        logger.error(f"Error listing ideas: {e}")
        raise _api_error(
            status_code=500,
            message="Failed to retrieve ideas",
            error_type="server_error",
            code="internal_error",
        ) from e


@router.post("/ideas")
async def create_idea(
    idea: IdeaCreate, auth_info: AuthInfo = Depends(require_scope("ideas.write"))
):
    """Create a new idea."""
    start_time = time.time()
    try:
        now = datetime.utcnow().isoformat()
        idea_data = {
            "idea_id": str(uuid.uuid4()),
            "user_id": auth_info["user_id"],
            "title": idea.title,
            "description": idea.description,
            "created_at": now,
            "updated_at": now,
            "is_published": False,
        }

        result = db_client.table("ideas").insert(idea_data).execute()
        created = _to_single_record(result.data)

        _record_usage(auth_info, endpoint="POST /ideas", response_code=201, start_time=start_time)
        return JSONResponse(status_code=201, content={"object": "idea", **format_idea(created)})
    except Exception as e:
        logger.error(f"Error creating idea: {e}")
        raise _api_error(
            status_code=500,
            message="Failed to create idea",
            error_type="server_error",
            code="internal_error",
        ) from e


@router.get("/ideas/{idea_id}")
async def get_idea(idea_id: str, auth_info: AuthInfo = Depends(require_scope("ideas.read"))):
    """Get a specific idea by ID."""
    start_time = time.time()
    try:
        idea = _get_user_idea_or_raise(idea_id, auth_info)

        _record_usage(
            auth_info, endpoint="GET /ideas/{id}", response_code=200, start_time=start_time
        )
        return {"object": "idea", **format_idea(idea)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting idea: {e}")
        raise _api_error(
            status_code=500,
            message="Failed to retrieve idea",
            error_type="server_error",
            code="internal_error",
        ) from e


@router.patch("/ideas/{idea_id}")
async def update_idea(
    idea_id: str, idea: IdeaUpdate, auth_info: AuthInfo = Depends(require_scope("ideas.write"))
):
    """Update an existing idea."""
    start_time = time.time()
    try:
        _get_user_idea_or_raise(idea_id, auth_info)

        update_data = {"updated_at": datetime.utcnow().isoformat()}
        if idea.title is not None:
            update_data["title"] = idea.title
        if idea.description is not None:
            update_data["description"] = idea.description

        result = (
            db_client.table("ideas").update(update_data).eq("idea_id", idea_id).single().execute()
        )
        updated = _to_single_record(result.data)

        if idea.title is not None or idea.description is not None:
            try:
                from app.services.ideas.collaboration import create_collaboration_service

                collab = create_collaboration_service(db_client)
                await collab.maybe_record_auto_version_after_user_edit(
                    idea_id, auth_info["user_id"]
                )
            except Exception as ver_exc:
                logger.warning(f"Auto-version after REST PATCH failed for {idea_id}: {ver_exc}")

        _record_usage(
            auth_info, endpoint="PATCH /ideas/{id}", response_code=200, start_time=start_time
        )
        return {"object": "idea", **format_idea(updated)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating idea: {e}")
        raise _api_error(
            status_code=500,
            message="Failed to update idea",
            error_type="server_error",
            code="internal_error",
        ) from e


@router.delete("/ideas/{idea_id}")
async def delete_idea(idea_id: str, auth_info: AuthInfo = Depends(require_scope("ideas.write"))):
    """Delete an idea."""
    start_time = time.time()
    try:
        _get_user_idea_or_raise(idea_id, auth_info)
        db_client.table("ideas").delete().eq("idea_id", idea_id).execute()

        _record_usage(
            auth_info, endpoint="DELETE /ideas/{id}", response_code=200, start_time=start_time
        )
        return {"deleted": True, "id": idea_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting idea: {e}")
        raise _api_error(
            status_code=500,
            message="Failed to delete idea",
            error_type="server_error",
            code="internal_error",
        ) from e


def _prepare_manager(idea: dict) -> ManifestManager:
    manager = ManifestManager()
    manager.set_idea(idea.get("description") or "")
    return manager


def _generate_business_model_canvas(manager: ManifestManager) -> Any:
    manager.bmc.update()
    return manager.bmc.summary or manager.get_business_model_canvas()


def _generate_pitch_deck(manager: ManifestManager) -> Any:
    return manager.generate_pitch_deck()


def _generate_prd(manager: ManifestManager) -> Any:
    return manager.generate_product_requirements_document()


def _generate_patent(manager: ManifestManager) -> Any:
    return ProvisionalPatent(manager).generate()


DocumentGenerator = Callable[[ManifestManager], Any]
DOCUMENT_GENERATORS: dict[str, tuple[str, DocumentGenerator]] = {
    "business_model_canvas": ("business_model_canvas", _generate_business_model_canvas),
    "pitch_deck": ("pitch_deck", _generate_pitch_deck),
    "prd": ("product_requirements_document", _generate_prd),
    "patent": ("provisional_patent", _generate_patent),
}


@router.post("/ideas/{idea_id}/generate")
async def generate_documents(
    idea_id: str,
    request: DocumentGenerate,
    auth_info: AuthInfo = Depends(require_scope("ideas.write")),
):
    """Generate documents for an idea (business model canvas, pitch deck, etc.)."""
    start_time = time.time()
    try:
        idea = _get_user_idea_or_raise(idea_id, auth_info)
        manager = _prepare_manager(idea)

        results: dict[str, dict[str, Any]] = {}

        for doc_type in request.document_types:
            generator_def = DOCUMENT_GENERATORS.get(doc_type)
            if not generator_def:
                continue

            result_key, generate = generator_def
            try:
                generated = generate(manager)
                results[result_key] = {"status": "generated" if generated else "failed"}
            except Exception as gen_err:
                logger.error(f"Error generating {doc_type}: {gen_err}")
                # Preserve existing error-key behavior for clients that may read doc_type aliases.
                results[doc_type] = {"status": "failed", "error": str(gen_err)}

        _record_usage(
            auth_info,
            endpoint="POST /ideas/{id}/generate",
            response_code=200,
            start_time=start_time,
            tokens_used=len(request.document_types) * 1000,
        )

        return {
            "object": "generation_result",
            "idea_id": idea_id,
            "documents": results,
            "status": "completed",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating documents: {e}")
        raise _api_error(
            status_code=500,
            message="Failed to generate documents",
            error_type="server_error",
            code="internal_error",
        ) from e


@router.get("/usage")
async def get_usage(auth_info: AuthInfo = Depends(api_key_auth)):
    """Get current API usage statistics."""
    try:
        stats = api_usage_service.get_usage_stats(auth_info["user_id"])
        return {"object": "usage", **stats}
    except Exception as e:
        logger.error(f"Error getting usage: {e}")
        raise _api_error(
            status_code=500,
            message="Failed to retrieve usage statistics",
            error_type="server_error",
            code="internal_error",
        ) from e
