"""Internal DSAR operations console (admin-only).

Surfaces the DSAR queue + breach-timer state to security/privacy
operators. Every route is gated by :func:`require_admin` (same gate as
the rest of the admin surface) and AUTH-tier rate-limited.

Endpoints:
- ``GET  /api/admin/dsar/requests``                  list queue
- ``POST /api/admin/dsar/requests``                  manually open
- ``POST /api/admin/dsar/requests/{id}/transition``  state-machine move
- ``GET  /api/admin/dsar/overdue``                   SLA breaches
- ``POST /api/admin/incidents/breach-timers``        open a breach clock
- ``GET  /api/admin/incidents/breach-timers``        active timers
- ``POST /api/admin/incidents/breach-timers/{id}/notify``
- ``POST /api/admin/incidents/breach-timers/{id}/close``

Documentation cross-references:
- docs/privacy/BREACH_NOTIFICATION.md (72h GDPR / 60d HIPAA windows)
- docs/security/INCIDENT_RESPONSE_RUNBOOK.md
"""

from __future__ import annotations

from typing import Any

from app.security.permissions import Principal, require_admin
from app.security.rate_limit_policies import TIER_AUTH, enforce_rate_limit
from app.services.compliance import breach_timers as breach_timer_service
from app.services.compliance import dsar_workflow as dsar_workflow_service
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field

router = APIRouter(prefix="/api/admin", tags=["admin", "dsar"], include_in_schema=False)


class OpenDsarRequest(BaseModel):
    type: str = Field(..., description="One of dsar_workflow_service.VALID_TYPES")
    subject_user_id: str | None = None
    subject_email: EmailStr | None = None
    jurisdiction: str | None = None
    notes: str | None = None
    sla_days: int | None = Field(None, ge=1, le=120)


class TransitionRequest(BaseModel):
    new_status: str
    notes: str | None = None
    assignee: str | None = None
    evidence_entry: dict[str, Any] | None = None


class OpenBreachTimerRequest(BaseModel):
    incident_id: str = Field(..., min_length=1, max_length=128)
    kind: str
    affected_count: int | None = Field(None, ge=0)
    affected_jurisdiction: str | None = None
    regulator: str | None = None
    notes: str | None = None


@router.get("/dsar/requests")
async def admin_list_dsar_requests(
    request: Request,
    status: str | None = Query(None),
    overdue_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    principal: Principal = Depends(require_admin),
) -> dict[str, Any]:
    enforce_rate_limit(request, "admin_dsar_list", tier=TIER_AUTH, user_id=principal.user_id)
    rows = dsar_workflow_service.list_requests(
        status=status, overdue_only=overdue_only, limit=limit
    )
    return {"count": len(rows), "requests": rows}


@router.post("/dsar/requests")
async def admin_open_dsar_request(
    request: Request,
    payload: OpenDsarRequest = Body(...),
    principal: Principal = Depends(require_admin),
) -> dict[str, Any]:
    enforce_rate_limit(request, "admin_dsar_open", tier=TIER_AUTH, user_id=principal.user_id)
    try:
        new_id = dsar_workflow_service.open_request(
            request_type=payload.type,
            subject_user_id=payload.subject_user_id,
            subject_email=payload.subject_email,
            jurisdiction=payload.jurisdiction,
            created_by=principal.user_id,
            notes=payload.notes,
            sla_days=payload.sla_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not new_id:
        raise HTTPException(status_code=503, detail="Datastore unavailable")
    return {"id": new_id, "status": "open"}


@router.post("/dsar/requests/{request_id}/transition")
async def admin_transition_dsar_request(
    request: Request,
    request_id: str,
    payload: TransitionRequest = Body(...),
    principal: Principal = Depends(require_admin),
) -> dict[str, Any]:
    enforce_rate_limit(request, "admin_dsar_transition", tier=TIER_AUTH, user_id=principal.user_id)
    try:
        ok = dsar_workflow_service.transition(
            request_id=request_id,
            new_status=payload.new_status,
            actor_id=principal.user_id,
            notes=payload.notes,
            assignee=payload.assignee,
            evidence_entry=payload.evidence_entry,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"id": request_id, "status": payload.new_status}


@router.get("/dsar/overdue")
async def admin_dsar_overdue(
    request: Request,
    within_hours: int = Query(0, ge=0, le=168),
    principal: Principal = Depends(require_admin),
) -> dict[str, Any]:
    enforce_rate_limit(request, "admin_dsar_overdue", tier=TIER_AUTH, user_id=principal.user_id)
    rows = dsar_workflow_service.find_overdue(window_hours=within_hours)
    return {"count": len(rows), "requests": rows}


@router.post("/incidents/breach-timers")
async def admin_open_breach_timer(
    request: Request,
    payload: OpenBreachTimerRequest = Body(...),
    principal: Principal = Depends(require_admin),
) -> dict[str, Any]:
    enforce_rate_limit(request, "admin_breach_open", tier=TIER_AUTH, user_id=principal.user_id)
    try:
        new_id = breach_timer_service.open_breach_timer(
            incident_id=payload.incident_id,
            kind=payload.kind,
            actor_id=principal.user_id,
            affected_count=payload.affected_count,
            affected_jurisdiction=payload.affected_jurisdiction,
            regulator=payload.regulator,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not new_id:
        raise HTTPException(status_code=503, detail="Datastore unavailable")
    return {"id": new_id, "status": "open"}


@router.get("/incidents/breach-timers")
async def admin_list_breach_timers(
    request: Request,
    within_hours: int = Query(72, ge=0, le=720),
    principal: Principal = Depends(require_admin),
) -> dict[str, Any]:
    enforce_rate_limit(request, "admin_breach_list", tier=TIER_AUTH, user_id=principal.user_id)
    rows = breach_timer_service.find_due(within_hours=within_hours)
    return {"count": len(rows), "timers": rows}


@router.post("/incidents/breach-timers/{timer_id}/notify")
async def admin_breach_notify(
    request: Request,
    timer_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    principal: Principal = Depends(require_admin),
) -> dict[str, Any]:
    enforce_rate_limit(request, "admin_breach_notify", tier=TIER_AUTH, user_id=principal.user_id)
    ok = breach_timer_service.record_notification(
        timer_id=timer_id, actor_id=principal.user_id, notes=payload.get("notes")
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Timer not found or already notified")
    return {"id": timer_id, "status": "notified"}


@router.post("/incidents/breach-timers/{timer_id}/close")
async def admin_breach_close(
    request: Request,
    timer_id: str,
    principal: Principal = Depends(require_admin),
) -> dict[str, Any]:
    enforce_rate_limit(request, "admin_breach_close", tier=TIER_AUTH, user_id=principal.user_id)
    ok = breach_timer_service.close_timer(timer_id=timer_id, actor_id=principal.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Timer not found or already closed")
    return {"id": timer_id, "status": "closed"}


__all__ = ["router"]
