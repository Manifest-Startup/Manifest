"""Shared FastAPI route dependencies."""

import hmac
import os

from app.utils.auth_utils import get_current_user_id
from fastapi import Depends, HTTPException, Request


def require_user_id(request: Request) -> str:
    """Resolve the authenticated user id from request auth context."""
    return get_current_user_id(request)


def require_admin(request: Request, user_id: str = Depends(require_user_id)) -> str:
    """Require admin role + enrolled MFA + a recent re-auth proof (SEC-029).

    Three checks, in order:
    1. principal.is_admin must be True.
    2. The admin must have TOTP MFA enrolled — admin accounts must
       NEVER be reachable with password alone.
    3. A recent step-up verification OR a fresh login (auth_iat) must
       cover the request.

    Heavy lifting delegates to the dedicated modules so this stays a
    thin orchestration layer.
    """
    from app.security.permissions import resolve_principal
    from app.security.step_up import (
        DEFAULT_TTL_SECONDS,
        _recent_login_satisfies,
        has_recent_step_up,
    )
    from app.services.identity.totp_mfa import get_user_mfa_status
    from app.utils.auth_utils import get_current_session_id_optional

    principal = resolve_principal(user_id)
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        mfa_enabled = bool(get_user_mfa_status(user_id).get("enabled"))
    except Exception:
        # Fail closed for admin surfaces if we cannot determine MFA state.
        raise HTTPException(status_code=503, detail="Admin MFA status unavailable") from None
    if not mfa_enabled:
        raise HTTPException(
            status_code=403,
            detail="MFA enrolment is required for admin accounts.",
            headers={"X-MFA-Required": "1"},
        )
    session_id = get_current_session_id_optional(request)
    if not (
        _recent_login_satisfies(request, DEFAULT_TTL_SECONDS)
        or has_recent_step_up(user_id, session_id, max_age_seconds=DEFAULT_TTL_SECONDS)
    ):
        raise HTTPException(
            status_code=401,
            detail="Re-authentication required",
            headers={"X-Step-Up-Required": "1"},
        )
    return user_id


def require_agent_loop_key(request: Request) -> str:
    """Validate the internal agent-loop secret for non-customer automation routes."""
    expected = os.getenv("MANIFEST_AGENT_LOOP_SECRET") or os.getenv("AGENT_LOOP_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="Internal agent loop is not configured")

    provided = request.headers.get("x-manifest-agent-key", "")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid agent loop key")

    return "internal-agent-loop"
