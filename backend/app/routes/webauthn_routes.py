"""WebAuthn passkey routes.

The four standard ceremonies plus a list/revoke pair. The verify endpoints
are gated behind ``ENABLE_WEBAUTHN`` because the ``webauthn`` package is
the trust root for passwordless login — accidentally accepting an
attestation from a wrong-origin or wrong-RP context would be silent
catastrophic auth bypass.
"""

from __future__ import annotations

from typing import Any

from app.routes.dependencies import require_user_id
from app.security.step_up import record_step_up
from app.services.security_audit_service import record_security_event
from app.services.webauthn_service import (
    begin_authentication,
    begin_registration,
    finish_authentication,
    finish_registration,
    list_credentials,
    revoke_credential,
    webauthn_enabled,
)
from app.utils.auth_utils import get_current_session_id_optional
from app.utils.logger import logger
from fastapi import APIRouter, Body, Depends, HTTPException, Request

router = APIRouter(prefix="/api/webauthn", tags=["WebAuthn"])


def _enabled_or_503() -> None:
    if not webauthn_enabled():
        raise HTTPException(
            status_code=503,
            detail="WebAuthn is not enabled in this deployment.",
        )


def _request_meta(request: Request) -> tuple[str | None, str | None]:
    client = getattr(request, "client", None)
    return (
        getattr(client, "host", None) if client else None,
        request.headers.get("user-agent"),
    )


@router.get("/credentials")
async def webauthn_list(user_id: str = Depends(require_user_id)) -> dict[str, Any]:
    return {"credentials": list_credentials(user_id), "enabled": webauthn_enabled()}


@router.post("/register/begin")
async def webauthn_register_begin(user_id: str = Depends(require_user_id)) -> dict[str, Any]:
    _enabled_or_503()
    from app.db.database import get_db_connection

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT email FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone() or {}
    email = row.get("email") or "user@manifeststartup.com"
    return begin_registration(user_id, email)


@router.post("/register/verify")
async def webauthn_register_verify(
    request: Request,
    body: dict[str, Any] = Body(...),
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    _enabled_or_503()
    credential = body.get("credential") or body
    nickname = body.get("nickname")
    try:
        result = finish_registration(user_id, credential, nickname=nickname)
    except ValueError as exc:
        record_security_event(
            "webauthn_register_failed",
            user_id=user_id,
            request_ip=_request_meta(request)[0],
            actor_id=user_id,
            actor_type="user",
            action="webauthn_register",
            target_type="webauthn_credential",
            target_id=user_id,
            outcome="failed",
            metadata={"reason": str(exc)},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[webauthn] register/verify error")
        raise HTTPException(status_code=500, detail="WebAuthn verification failed") from exc
    record_security_event(
        "webauthn_credential_registered",
        user_id=user_id,
        request_ip=_request_meta(request)[0],
        actor_id=user_id,
        actor_type="user",
        action="webauthn_register",
        target_type="webauthn_credential",
        target_id=str(result["credential_db_id"]),
        outcome="success",
        metadata={"credential_db_id": result["credential_db_id"]},
    )
    return result


@router.post("/authenticate/begin")
async def webauthn_authenticate_begin(user_id: str = Depends(require_user_id)) -> dict[str, Any]:
    _enabled_or_503()
    try:
        return begin_authentication(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/authenticate/verify")
async def webauthn_authenticate_verify(
    request: Request,
    body: dict[str, Any] = Body(...),
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    _enabled_or_503()
    credential = body.get("credential") or body
    try:
        result = finish_authentication(user_id, credential)
    except ValueError as exc:
        record_security_event(
            "webauthn_authn_failed",
            user_id=user_id,
            request_ip=_request_meta(request)[0],
            actor_id=user_id,
            actor_type="user",
            action="webauthn_authenticate",
            target_type="user",
            target_id=user_id,
            outcome="failed",
            metadata={"reason": str(exc)},
        )
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[webauthn] authn/verify error")
        raise HTTPException(status_code=500, detail="WebAuthn verification failed") from exc
    # Successful WebAuthn verify counts as a step-up proof.
    session_id = get_current_session_id_optional(request)
    ip, ua = _request_meta(request)
    verification_id = record_step_up(
        user_id, session_id=session_id, method="webauthn", request_ip=ip, user_agent=ua
    )
    record_security_event(
        "webauthn_authn_success",
        user_id=user_id,
        session_id=session_id,
        request_ip=ip,
        actor_id=user_id,
        actor_type="user",
        action="webauthn_authenticate",
        target_type="user",
        target_id=user_id,
        outcome="success",
        metadata={
            "credential_db_id": result["credential_db_id"],
            "verification_id": verification_id,
        },
    )
    return {**result, "step_up_verification_id": verification_id}


@router.delete("/credentials/{credential_id}")
async def webauthn_delete(
    credential_id: str, user_id: str = Depends(require_user_id)
) -> dict[str, Any]:
    if not revoke_credential(user_id, credential_id):
        raise HTTPException(status_code=404, detail="Credential not found")
    record_security_event(
        "webauthn_credential_revoked",
        user_id=user_id,
        actor_id=user_id,
        actor_type="user",
        action="webauthn_revoke",
        target_type="webauthn_credential",
        target_id=str(credential_id),
        outcome="success",
        metadata={"credential_db_id": credential_id},
    )
    return {"revoked": True}
