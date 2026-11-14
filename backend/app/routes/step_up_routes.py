"""Step-up authentication endpoints (SEC-025/026).

Lets a logged-in user re-prove identity (password or TOTP) so they can
perform a sensitive action within a short verification window — without
having to fully re-login.
"""

from __future__ import annotations

from app.db.database import get_db_connection
from app.routes.dependencies import require_user_id
from app.security.step_up import DEFAULT_TTL_SECONDS, record_step_up
from app.services.security_audit_service import record_security_event
from app.utils.auth_utils import get_current_session_id_optional
from app.utils.logger import logger
from app.utils.password_utils import verify_password
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/auth/step-up", tags=["Step-Up Auth"])


class StepUpPasswordRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=512)


class StepUpTotpRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=10)


def _request_meta(request: Request):
    client = getattr(request, "client", None)
    return (
        getattr(client, "host", None) if client else None,
        request.headers.get("user-agent"),
    )


@router.post("/password")
async def step_up_password(
    req: StepUpPasswordRequest,
    request: Request,
    user_id: str = Depends(require_user_id),
):
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM users WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
    except Exception as exc:
        logger.warning("[step_up] user lookup failed: %s", exc)
        raise HTTPException(status_code=500, detail="Step-up unavailable") from exc

    pw_hash = (row or {}).get("password_hash") if row else None
    if not pw_hash or not verify_password(req.password, pw_hash):
        record_security_event(
            "step_up_password_failed",
            user_id=user_id,
            request_ip=_request_meta(request)[0],
            actor_id=user_id,
            actor_type="user",
            action="step_up",
            target_type="user",
            target_id=user_id,
            outcome="failed",
        )
        try:
            from app.security.audit_detections import detect_mfa_bypass_attempt

            detect_mfa_bypass_attempt(
                user_id=user_id,
                request_ip=_request_meta(request)[0],
                reason="step_up_password_failed",
            )
        except Exception:  # pragma: no cover - detector is best-effort
            pass
        raise HTTPException(status_code=401, detail="Re-authentication failed")

    session_id = get_current_session_id_optional(request)
    ip, ua = _request_meta(request)
    verification_id = record_step_up(
        user_id, session_id=session_id, method="password", request_ip=ip, user_agent=ua
    )
    record_security_event(
        "step_up_password_success",
        user_id=user_id,
        session_id=session_id,
        request_ip=ip,
        actor_id=user_id,
        actor_type="user",
        action="step_up",
        target_type="user",
        target_id=user_id,
        outcome="success",
        metadata={"verification_id": verification_id},
    )
    return {
        "verified": True,
        "verification_id": verification_id,
        "ttl_seconds": DEFAULT_TTL_SECONDS,
    }


@router.post("/totp")
async def step_up_totp(
    req: StepUpTotpRequest,
    request: Request,
    user_id: str = Depends(require_user_id),
):
    try:
        from app.services.totp_mfa_service import verify_user_mfa_code
    except ImportError:
        raise HTTPException(status_code=501, detail="TOTP step-up not available") from None
    try:
        ok = verify_user_mfa_code(user_id, req.code)
    except Exception as exc:
        logger.warning("[step_up] TOTP verify error: %s", exc)
        ok = False
    if not ok:
        record_security_event(
            "step_up_totp_failed",
            user_id=user_id,
            request_ip=_request_meta(request)[0],
            actor_id=user_id,
            actor_type="user",
            action="step_up",
            target_type="user",
            target_id=user_id,
            outcome="failed",
        )
        try:
            from app.security.audit_detections import detect_mfa_bypass_attempt

            detect_mfa_bypass_attempt(
                user_id=user_id,
                request_ip=_request_meta(request)[0],
                reason="step_up_totp_failed",
            )
        except Exception:  # pragma: no cover - detector is best-effort
            pass
        raise HTTPException(status_code=401, detail="Invalid TOTP code")
    session_id = get_current_session_id_optional(request)
    ip, ua = _request_meta(request)
    verification_id = record_step_up(
        user_id, session_id=session_id, method="totp", request_ip=ip, user_agent=ua
    )
    record_security_event(
        "step_up_totp_success",
        user_id=user_id,
        session_id=session_id,
        request_ip=ip,
        actor_id=user_id,
        actor_type="user",
        action="step_up",
        target_type="user",
        target_id=user_id,
        outcome="success",
        metadata={"verification_id": verification_id},
    )
    return {
        "verified": True,
        "verification_id": verification_id,
        "ttl_seconds": DEFAULT_TTL_SECONDS,
    }
