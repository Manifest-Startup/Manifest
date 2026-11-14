"""
API Key Management Routes

Endpoints for creating, viewing, and revoking API keys.
Used by the Account Settings UI.
"""

from app.routes.dependencies import require_user_id
from app.security.permissions import filter_api_key_scopes
from app.security.step_up import require_recent_auth
from app.services.compliance.security_audit import record_security_event
from app.services.identity.api_keys import (
    DEFAULT_API_KEY_SCOPES,
    BillingTier,
    api_key_service,
    api_usage_service,
)
from app.utils.logger import logger
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/keys", tags=["API Keys"])


class CreateClientRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Name for the API client")


class CreateKeyRequest(BaseModel):
    client_id: str = Field(..., description="The API client ID")
    name: str = Field(default="Default Key", max_length=100, description="Name for the key")
    expires_days: int | None = Field(None, ge=1, le=365, description="Days until expiration")
    scopes: list[str] | None = Field(
        default=None,
        description="Permission scopes granted to this key (subset of caller's permissions).",
    )


class RotateKeyRequest(BaseModel):
    key_id: str = Field(..., description="The existing key ID to rotate")
    overlap_seconds: int = Field(
        default=86400,
        ge=60,
        le=14 * 24 * 60 * 60,
        description="How long the old key keeps working after rotation (default 24 h).",
    )


@router.get("/clients")
async def list_clients(user_id: str = Depends(require_user_id)):
    """List all API clients for the current user."""
    try:
        clients = api_key_service.get_api_clients(user_id)

        for client in clients:
            keys = api_key_service.get_api_keys(client["id"])
            client["keys"] = [
                {
                    "id": k["id"],
                    "name": k["name"],
                    "key_prefix": k["key_prefix"],
                    "status": k["status"],
                    "created_at": k["created_at"],
                    "last_used_at": k["last_used_at"],
                    "expires_at": k["expires_at"],
                }
                for k in keys
            ]

        return {"clients": clients}
    except Exception as e:
        logger.error(f"Error listing clients: {e}")
        raise HTTPException(status_code=500, detail="Failed to list API clients") from e


@router.post("/clients")
async def create_client(req: CreateClientRequest, user_id: str = Depends(require_user_id)):
    """Create a new API client."""
    try:
        client = api_key_service.create_api_client(user_id, req.name)
        record_security_event(
            "api_client_created",
            user_id=user_id,
            action="api_client_create",
            target_type="api_client",
            target_id=str(client.get("id") or ""),
            outcome="success",
            metadata={"client_id": client.get("id"), "name": req.name},
        )
        return {"client": client}
    except Exception as e:
        logger.error(f"Error creating client: {e}")
        raise HTTPException(status_code=500, detail="Failed to create API client") from e


@router.post("/keys")
async def create_key(req: CreateKeyRequest, user_id: str = Depends(require_recent_auth())):
    """Create a new API key for a client."""
    try:
        client = api_key_service.get_api_client(req.client_id)
        if not client:
            raise HTTPException(status_code=404, detail="API client not found")

        if client["user_id"] != user_id:
            raise HTTPException(
                status_code=403, detail="Not authorized to create keys for this client"
            )

        scopes = filter_api_key_scopes(req.scopes or DEFAULT_API_KEY_SCOPES)
        key = api_key_service.create_api_key(
            req.client_id, req.name, req.expires_days, scopes=scopes
        )
        record_security_event(
            "api_key_created",
            user_id=user_id,
            actor_id=user_id,
            actor_type="user",
            action="api_key_create",
            target_type="api_key",
            target_id=str(key.get("id") or ""),
            outcome="success",
            metadata={
                "client_id": req.client_id,
                "key_id": key.get("id"),
                "name": req.name,
                "scopes": scopes,
            },
        )

        return {
            "key": {
                "id": key["id"],
                "name": key["name"],
                "key_prefix": key["key_prefix"],
                "full_key": key["full_key"],
                "scopes": key.get("scopes") or scopes,
                "created_at": key["created_at"],
                "expires_at": key.get("expires_at"),
            },
            "message": "Store this key securely. You won't be able to see it again.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating key: {e}")
        raise HTTPException(status_code=500, detail="Failed to create API key") from e


@router.post("/keys/rotate")
async def rotate_key(req: RotateKeyRequest, user_id: str = Depends(require_recent_auth())):
    """Rotate an API key. Returns the new full key once; old key keeps
    working for ``overlap_seconds`` so callers can swap with no downtime."""
    try:
        result = api_key_service.rotate_api_key(
            req.key_id, user_id, overlap_seconds=req.overlap_seconds
        )
        if not result:
            raise HTTPException(status_code=404, detail="Key not found or not authorized")
        record_security_event(
            "api_key_rotated",
            user_id=user_id,
            actor_id=user_id,
            actor_type="user",
            action="api_key_rotate",
            target_type="api_key",
            target_id=str(req.key_id),
            outcome="success",
            metadata={
                "old_key_id": req.key_id,
                "new_key_id": result["new_key"].get("id"),
                "expires_at": result["expires_at"],
            },
        )
        return {
            "old_key_id": req.key_id,
            "expires_at": result["expires_at"],
            "new_key": {
                "id": result["new_key"]["id"],
                "name": result["new_key"]["name"],
                "key_prefix": result["new_key"]["key_prefix"],
                "full_key": result["new_key"]["full_key"],
                "scopes": result["new_key"].get("scopes"),
            },
            "message": "Old key remains valid until expires_at; rotate clients before then.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error rotating key: {exc}")
        raise HTTPException(status_code=500, detail="Failed to rotate API key") from exc


@router.delete("/keys/{key_id}")
async def revoke_key(key_id: str, user_id: str = Depends(require_recent_auth())):
    """Revoke an API key."""
    try:
        success = api_key_service.revoke_api_key(key_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Key not found or not authorized")
        record_security_event(
            "api_key_revoked",
            user_id=user_id,
            action="api_key_revoke",
            target_type="api_key",
            target_id=str(key_id),
            outcome="success",
            metadata={"key_id": key_id},
        )
        return {"revoked": True, "key_id": key_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking key: {e}")
        raise HTTPException(status_code=500, detail="Failed to revoke API key") from e


@router.delete("/clients/{client_id}")
async def delete_client(client_id: str, user_id: str = Depends(require_recent_auth())):
    """Delete an API client and all its keys."""
    try:
        success = api_key_service.delete_api_client(client_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Client not found or not authorized")
        record_security_event(
            "api_client_deleted",
            user_id=user_id,
            action="api_client_delete",
            target_type="api_client",
            target_id=str(client_id),
            outcome="success",
            metadata={"client_id": client_id},
        )
        return {"deleted": True, "client_id": client_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting client: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete API client") from e


@router.get("/usage")
async def get_usage(user_id: str = Depends(require_user_id)):
    """Get API usage statistics for the current user."""
    try:
        stats = api_usage_service.get_usage_stats(user_id)
        return {"usage": stats}
    except Exception as e:
        logger.error(f"Error getting usage: {e}")
        raise HTTPException(status_code=500, detail="Failed to get usage statistics") from e


@router.get("/tiers")
async def get_tiers():
    """Get available billing tiers and their limits."""
    return {
        "tiers": [
            {
                "id": BillingTier.FREE,
                "name": "Free",
                "price": 0,
                "requests_per_month": BillingTier.LIMITS[BillingTier.FREE]["requests_per_month"],
                "rate_limit_per_minute": BillingTier.LIMITS[BillingTier.FREE][
                    "rate_limit_per_minute"
                ],
                "features": ["Basic API access", "Community support"],
            },
            {
                "id": BillingTier.STARTER,
                "name": "Starter",
                "price": 29,
                "requests_per_month": BillingTier.LIMITS[BillingTier.STARTER]["requests_per_month"],
                "rate_limit_per_minute": BillingTier.LIMITS[BillingTier.STARTER][
                    "rate_limit_per_minute"
                ],
                "features": ["Email support", "Higher rate limits", "Usage analytics"],
            },
            {
                "id": BillingTier.PRO,
                "name": "Pro",
                "price": 99,
                "requests_per_month": BillingTier.LIMITS[BillingTier.PRO]["requests_per_month"],
                "rate_limit_per_minute": BillingTier.LIMITS[BillingTier.PRO][
                    "rate_limit_per_minute"
                ],
                "features": ["Priority support", "Advanced analytics", "Custom integrations"],
            },
            {
                "id": BillingTier.ENTERPRISE,
                "name": "Enterprise",
                "price": -1,
                "requests_per_month": -1,
                "rate_limit_per_minute": BillingTier.LIMITS[BillingTier.ENTERPRISE][
                    "rate_limit_per_minute"
                ],
                "features": [
                    "Dedicated support",
                    "Custom limits",
                    "SLA guarantee",
                    "On-premise option",
                ],
            },
        ]
    }
