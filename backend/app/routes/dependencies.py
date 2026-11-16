"""Shared FastAPI route dependencies."""

import hmac
import os

from app.auth.current_user import require_user_id
from fastapi import Depends, HTTPException, Request


def require_admin(request: Request, user_id: str = Depends(require_user_id)) -> str:
    """Require the admin role and a recent sign-in (SEC-029).

    1. principal.is_admin must be True.
    2. The session must come from a fresh "Continue with Open Media" sign-in
       (``auth_iat``) or a still-valid step-up row. Second factors live in Open
       Media now (ADR 0002), so Manifest no longer checks its own TOTP enrolment.
    """
    from app.auth.current_user import get_current_session_id_optional
    from app.security.permissions import resolve_principal
    from app.security.step_up import (
        DEFAULT_TTL_SECONDS,
        _recent_login_satisfies,
        has_recent_step_up,
    )

    principal = resolve_principal(user_id)
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
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
