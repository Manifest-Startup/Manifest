"""
Data Subject Access Request (DSAR) API.

Implements the formal entry points required by GDPR Arts. 15-21 and
CCPA / CPRA §§1798.100-1798.130. Every endpoint is authenticated, rate
limited at the route layer (T19), audited via the chained security log
(T14) and — for the destructive paths — backed by the crypto-shred
primitive in ``app.services.compliance.tenant_purge`` (T3).

Endpoints
---------
- ``GET    /api/dsar/access``           — right of access (Art. 15)
- ``GET    /api/dsar/portability``      — right to portability (Art. 20)
- ``POST   /api/dsar/rectify``          — right of rectification (Art. 16)
- ``POST   /api/dsar/object``           — right to object / opt-out
                                         of analytics + comms (Art. 21,
                                         CCPA §1798.120)
- ``POST   /api/dsar/erase``            — right to erasure (Art. 17,
                                         CCPA §1798.105)
- ``GET    /api/dsar/erase/certificate``— retrieve the deletion
                                         certificate proof (post-erase)

Design notes
------------
- Erasure performs hard delete via :func:`purge_tenant`. It crypto-shreds
  the user's wrapped DEK and tombstones the row in a single transaction.
  We never expose a "soft delete" pathway here.
- Every successful response writes a canonical security audit event so
  the DSAR fulfilment timeline is provable for auditors.
- Deletion responses include a tamper-evident certificate (UUID, SHA-256
  of the per-table count summary, the audit event id, completed-at).
- Access/portability responses are explicit JSON envelopes — never raw
  ORM rows — to keep the schema stable for regulators and to prevent
  accidental exposure of new internal columns over time.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.database import get_database_url, get_db_connection
from app.routes.dependencies import require_user_id
from app.security.rate_limit_policies import TIER_AUTH, enforce_rate_limit
from app.security.step_up import require_recent_auth
from app.services.compliance.retention_exceptions import (
    public_view as retention_exceptions_public_view,
)
from app.services.compliance.security_audit import record_security_event
from app.services.compliance.tenant_purge import purge_tenant
from app.utils.logger import logger
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

router = APIRouter(prefix="/api/dsar", tags=["privacy", "dsar"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    client = getattr(request, "client", None)
    return getattr(client, "host", None) if client else None


def _user_agent(request: Request) -> str | None:
    ua = request.headers.get("user-agent")
    return ua[:500] if ua else None


class DSARDataExtractionError(RuntimeError):
    """Raised when a *required* DSAR data category cannot be read.

    Required = the subject profile and the configured-required category
    list. Raising this maps to a 503 + failure audit event in the route
    so we never return a misleading HTTP 200 with empty payload.
    """


def _fetchall_safe(
    sql: str,
    params: tuple = (),
    *,
    errors: dict[str, str] | None = None,
    label: str | None = None,
) -> list[dict[str, Any]]:
    """Execute a read-only query for an *optional* DSAR category.

    Optional categories may legitimately be absent in older deployments
    (table not yet created, peripheral feature off). On error we return
    [] AND record the error against ``label`` in ``errors`` so the
    response can advertise ``partial=true`` and the caller can audit a
    non-success outcome. If the database is not configured at all, we
    return [] silently — that is a deployment-level state, not a
    per-request failure.
    """
    if not get_database_url():
        return []
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() or []
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("[dsar] read query failed for %s: %s", label, exc)
        if errors is not None and label:
            errors[label] = str(exc)[:200]
        return []


def _fetchall_required(sql: str, params: tuple, *, label: str) -> list[dict[str, Any]]:
    """Execute a read-only query for a *required* DSAR category.

    Any failure (DB unavailable, query error, schema mismatch) raises
    :class:`DSARDataExtractionError`. The route handler converts that
    into a 503 and a failure audit event so the user is never told
    "here is your data" with silently missing core records.
    """
    if not get_database_url():
        raise DSARDataExtractionError(f"datastore_unavailable:{label}")
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() or []
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.exception("[dsar] required read failed for %s", label)
        raise DSARDataExtractionError(f"{label}:{exc}") from exc


def _user_row(user_id: str) -> dict[str, Any]:
    """Fetch the subject profile. Required — failure raises."""
    rows = _fetchall_required(
        """
        SELECT user_id, email, first_name, last_name, created_at,
               disabled_at, disabled_reason, deletion_requested_at,
               role, is_admin
        FROM users
        WHERE user_id = %s
        LIMIT 1
        """,
        (user_id,),
        label="profile",
    )
    return rows[0] if rows else {}


def _collect_subject_data(user_id: str) -> dict[str, Any]:
    """Build the canonical DSAR data envelope for ``user_id``.

    Required categories (profile, sessions, privacy_consents) raise
    :class:`DSARDataExtractionError` on failure — they are the spine of
    a defensible right-of-access response. Optional categories
    (mfa_factors, webauthn_credentials, integrations, api_keys) record
    a per-category error and the envelope advertises ``partial=true``
    plus an ``errors`` map so the caller can mark the audit outcome
    accordingly.
    """
    errors: dict[str, str] = {}
    profile = _user_row(user_id)
    sessions = _fetchall_required(
        "SELECT session_id, created_at, last_seen_at, ip_hash, "
        "user_agent, revoked_at FROM user_sessions WHERE user_id = %s",
        (user_id,),
        label="sessions",
    )
    privacy_consents = _fetchall_required(
        "SELECT policy_version, source, analytics_enabled, "
        "communications_enabled, do_not_sell_or_share, "
        "consent_payload, consent_updated_at "
        "FROM privacy_consents WHERE user_id = %s "
        "ORDER BY consent_updated_at DESC",
        (user_id,),
        label="privacy_consents",
    )
    categories: dict[str, Any] = {
        "sessions": sessions,
        "mfa_factors": _fetchall_safe(
            "SELECT factor_type, label, created_at, last_used_at "
            "FROM user_totp_mfa WHERE user_id = %s",
            (user_id,),
            errors=errors,
            label="mfa_factors",
        ),
        "webauthn_credentials": _fetchall_safe(
            "SELECT credential_id, label, created_at, last_used_at "
            "FROM webauthn_credentials WHERE user_id = %s",
            (user_id,),
            errors=errors,
            label="webauthn_credentials",
        ),
        "privacy_consents": privacy_consents,
        "integrations": _fetchall_safe(
            "SELECT provider, created_at, updated_at, status "
            "FROM integrations WHERE user_id = %s",
            (user_id,),
            errors=errors,
            label="integrations",
        ),
        "api_keys": _fetchall_safe(
            "SELECT key_id, label, created_at, last_used_at, revoked_at "
            "FROM api_keys WHERE user_id = %s",
            (user_id,),
            errors=errors,
            label="api_keys",
        ),
    }
    return {
        "schema_version": "1.0",
        "generated_at": _now_iso(),
        "subject": {"user_id": user_id, "profile": profile},
        "categories": categories,
        "partial": bool(errors),
        "errors": errors,
        "notes": (
            "Field-level ciphertext columns (e.g. integration tokens) "
            "are crypto-shredded on erasure and are not exported in "
            "plaintext here. Contact privacy@manifest.example for an "
            "out-of-band copy under DPA scope."
        ),
    }


def _emit_dsar_event(
    *,
    action: str,
    user_id: str,
    request: Request,
    outcome: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    record_security_event(
        "dsar_request",
        user_id=user_id,
        request_ip=_client_ip(request),
        user_agent=_user_agent(request),
        actor_id=user_id,
        actor_type="user",
        action=action,
        target_type="user",
        target_id=user_id,
        outcome=outcome,
        metadata=metadata or {},
    )


def _resolve_jurisdiction(request: Request) -> str | None:
    """Best-effort jurisdiction string for the current request, used to
    pin the statutory SLA on the workflow row. Falls back to ``None``
    on any error so a self-service flow still completes (with the
    default 30d GDPR window)."""
    try:
        from app.services.compliance.privacy_jurisdiction import resolve_default_consent_for

        return resolve_default_consent_for(request).jurisdiction
    except Exception:  # pragma: no cover
        return None


def _record_workflow_row(
    *,
    request: Request,
    request_type: str,
    user_id: str,
    audit_event_id: str | None = None,
) -> None:
    """Persist the queue-entry mirror row for a self-service DSAR flow.

    Persistence is *required* for SOC2/GDPR/CCPA evidence (the audit
    chain proves the action ran; the workflow row proves operations had
    a queue entry to action). If the write fails — DB outage,
    constraint violation, anything — we **explicitly emit a failure
    audit event** (``dsar_workflow_persist_failed``) so the gap is
    visible in SIEM rather than swallowed silently. The user-facing
    request still completes, because the actual data action already
    succeeded; refusing the response would mean a successful erasure
    with a 5xx telling the user to retry.
    """
    jurisdiction = _resolve_jurisdiction(request)
    persist_failed = False
    persist_error: str | None = None
    new_id: str | None = None
    try:
        from app.services.compliance.dsar_workflow import open_request as _open_dsar

        new_id = _open_dsar(
            request_type=request_type,
            subject_user_id=user_id,
            jurisdiction=jurisdiction,
            created_by=user_id,
            audit_event_id=audit_event_id,
            auto_complete=True,
        )
        if new_id is None:
            persist_failed = True
            persist_error = "open_request_returned_none"
    except Exception as exc:
        persist_failed = True
        persist_error = str(exc)[:200]
        logger.warning("[dsar] workflow row creation raised (%s)", request_type, exc_info=True)
    if persist_failed:
        _emit_dsar_event(
            action="dsar_workflow_persist_failed",
            user_id=user_id,
            request=request,
            outcome="failure",
            metadata={
                "request_type": request_type,
                "jurisdiction": jurisdiction,
                "error": persist_error,
            },
        )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RectifyRequest(BaseModel):
    # ``full_name`` is accepted for backwards compatibility with older
    # clients but is split into first_name/last_name on the server side
    # because that's the canonical schema in the users table.
    full_name: str | None = Field(default=None, max_length=200)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None


class ObjectRequest(BaseModel):
    """Right to object / opt-out (GDPR Art. 21, CCPA §1798.120).

    The flags follow the consent-ledger contract so this endpoint shares
    storage with /api/privacy/consent.
    """

    analytics_enabled: bool = False
    communications_enabled: bool = False
    do_not_sell_or_share: bool = True
    reason: str | None = Field(default=None, max_length=500)


class EraseRequest(BaseModel):
    confirm_email: str
    acknowledge_irreversible: bool = False


class DeletionCertificate(BaseModel):
    certificate_id: str
    user_id: str
    completed_at: str
    summary_sha256: str
    audit_event: str
    counts: dict[str, int]
    method: str = "crypto_shred+hard_delete"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/access")
async def dsar_access(
    request: Request,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    """GDPR Art. 15 — right of access.

    Returns a structured JSON envelope listing every category of personal
    data Manifest holds about the caller. Idempotent and audited.
    Rate-limited at the AUTH tier to prevent envelope-scraping by an
    attacker with a stolen cookie.
    """
    enforce_rate_limit(request, "dsar_access", tier=TIER_AUTH, user_id=user_id)
    try:
        envelope = _collect_subject_data(user_id)
    except DSARDataExtractionError as exc:
        _emit_dsar_event(
            action="dsar_access",
            user_id=user_id,
            request=request,
            outcome="failure",
            metadata={"error": str(exc)[:200], "stage": "required_extraction"},
        )
        raise HTTPException(
            status_code=503,
            detail="DSAR access could not be fulfilled: required data unavailable.",
        ) from exc
    outcome = "partial" if envelope.get("partial") else "success"
    _emit_dsar_event(
        action="dsar_access",
        user_id=user_id,
        request=request,
        outcome=outcome,
        metadata={
            "categories": list(envelope["categories"].keys()),
            "partial": envelope.get("partial", False),
            "errors": list((envelope.get("errors") or {}).keys()),
        },
    )
    _record_workflow_row(request=request, request_type="access", user_id=user_id)
    return envelope


@router.get("/portability")
async def dsar_portability(
    request: Request,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    """GDPR Art. 20 — right to portability.

    Same payload as /access but advertised as a portable export the user
    may transmit to another controller. Rate-limited at the AUTH tier.
    """
    enforce_rate_limit(request, "dsar_portability", tier=TIER_AUTH, user_id=user_id)
    try:
        envelope = _collect_subject_data(user_id)
    except DSARDataExtractionError as exc:
        _emit_dsar_event(
            action="dsar_portability",
            user_id=user_id,
            request=request,
            outcome="failure",
            metadata={"error": str(exc)[:200], "stage": "required_extraction"},
        )
        raise HTTPException(
            status_code=503,
            detail="DSAR portability could not be fulfilled: required data unavailable.",
        ) from exc
    envelope["format"] = "application/json; profile=manifest-dsar/1.0"
    outcome = "partial" if envelope.get("partial") else "success"
    _emit_dsar_event(
        action="dsar_portability",
        user_id=user_id,
        request=request,
        outcome=outcome,
        metadata={
            "format": envelope["format"],
            "partial": envelope.get("partial", False),
            "errors": list((envelope.get("errors") or {}).keys()),
        },
    )
    _record_workflow_row(request=request, request_type="portability", user_id=user_id)
    return envelope


@router.post("/rectify")
async def dsar_rectify(
    request: Request,
    payload: RectifyRequest = Body(...),
    user_id: str = Depends(require_recent_auth()),
) -> dict[str, Any]:
    """GDPR Art. 16 — right of rectification.

    Currently scoped to user-controllable profile fields. Requires a
    recent re-auth proof and AUTH-tier rate limiting. Email changes
    invalidate sessions to force re-verification on the new identity.
    """
    enforce_rate_limit(request, "dsar_rectify", tier=TIER_AUTH, user_id=user_id)
    updates: dict[str, Any] = {}
    if payload.first_name is not None:
        updates["first_name"] = payload.first_name.strip() or None
    if payload.last_name is not None:
        updates["last_name"] = payload.last_name.strip() or None
    # Backwards-compat: split a legacy full_name into first/last only if
    # the caller didn't already supply the split fields.
    if payload.full_name is not None and "first_name" not in updates and "last_name" not in updates:
        cleaned = payload.full_name.strip()
        if cleaned:
            parts = cleaned.split(None, 1)
            updates["first_name"] = parts[0]
            updates["last_name"] = parts[1] if len(parts) > 1 else None
        else:
            updates["first_name"] = None
            updates["last_name"] = None
    if payload.email is not None:
        updates["email"] = str(payload.email).strip().lower()

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to rectify")

    if not get_database_url():
        raise HTTPException(status_code=503, detail="Datastore unavailable")

    set_clause = ", ".join(f"{col} = %s" for col in updates)
    params = list(updates.values()) + [user_id]
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE users SET {set_clause}, updated_at = NOW() " "WHERE user_id = %s",
                    tuple(params),
                )
            conn.commit()
    except Exception as exc:
        logger.exception("[dsar] rectify failed for user_id=%s", user_id)
        _emit_dsar_event(
            action="dsar_rectify",
            user_id=user_id,
            request=request,
            outcome="failure",
            metadata={"error": str(exc)[:200]},
        )
        raise HTTPException(status_code=500, detail="Rectification failed") from exc

    _emit_dsar_event(
        action="dsar_rectify",
        user_id=user_id,
        request=request,
        outcome="success",
        metadata={"fields": sorted(updates.keys())},
    )
    _record_workflow_row(request=request, request_type="rectification", user_id=user_id)
    return {"updated": sorted(updates.keys()), "completed_at": _now_iso()}


@router.post("/object")
async def dsar_object(
    request: Request,
    payload: ObjectRequest = Body(...),
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    """GDPR Art. 21 / CCPA §1798.120 — right to object / opt-out.

    Writes a fresh, append-only row to ``privacy_consents`` so the
    objection event is provable in the ledger. Rate limited at the
    AUTH tier to prevent ledger flooding.
    """
    enforce_rate_limit(request, "dsar_object", tier=TIER_AUTH, user_id=user_id)
    if not get_database_url():
        raise HTTPException(status_code=503, detail="Datastore unavailable")

    consent_payload = {
        "analytics_enabled": payload.analytics_enabled,
        "communications_enabled": payload.communications_enabled,
        "do_not_sell_or_share": payload.do_not_sell_or_share,
        "reason": payload.reason,
        "via": "dsar_object",
    }
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO privacy_consents (
                        user_id, source, policy_version,
                        analytics_enabled, communications_enabled,
                        do_not_sell_or_share, consent_payload
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        user_id,
                        "dsar_object",
                        os.getenv("MANIFEST_PRIVACY_POLICY_VERSION", "2026-04"),
                        payload.analytics_enabled,
                        payload.communications_enabled,
                        payload.do_not_sell_or_share,
                        json.dumps(consent_payload),
                    ),
                )
            conn.commit()
    except Exception as exc:
        logger.exception("[dsar] object failed for user_id=%s", user_id)
        _emit_dsar_event(
            action="dsar_object",
            user_id=user_id,
            request=request,
            outcome="failure",
            metadata={"error": str(exc)[:200]},
        )
        raise HTTPException(status_code=500, detail="Objection failed") from exc

    # Mirror the objection into the DSAR workflow ledger so it gets the
    # same statutory-SLA tracking, deadline checks, and admin queue
    # visibility as access/portability/rectification/erasure requests.
    _record_workflow_row(request=request, request_type="objection", user_id=user_id)
    _emit_dsar_event(
        action="dsar_object",
        user_id=user_id,
        request=request,
        outcome="success",
        metadata={
            "analytics_enabled": payload.analytics_enabled,
            "communications_enabled": payload.communications_enabled,
            "do_not_sell_or_share": payload.do_not_sell_or_share,
        },
    )
    return {
        "recorded_at": _now_iso(),
        "preferences": {
            "analytics_enabled": payload.analytics_enabled,
            "communications_enabled": payload.communications_enabled,
            "do_not_sell_or_share": payload.do_not_sell_or_share,
        },
    }


def _build_certificate(
    user_id: str, counts: dict[str, int], audit_event_id: str
) -> DeletionCertificate:
    summary = json.dumps(counts, sort_keys=True, default=str)
    digest = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    return DeletionCertificate(
        certificate_id=str(uuid.uuid4()),
        user_id=user_id,
        completed_at=_now_iso(),
        summary_sha256=digest,
        audit_event=audit_event_id,
        counts=counts,
    )


@router.post("/erase")
async def dsar_erase(
    request: Request,
    payload: EraseRequest = Body(...),
    user_id: str = Depends(require_recent_auth()),
) -> dict[str, Any]:
    """GDPR Art. 17 / CCPA §1798.105 — right to erasure.

    Defence in depth:
    - Authenticated session **plus** recent re-auth proof
      (``require_recent_auth``) — a stolen long-lived cookie alone is
      not enough.
    - Per-user + per-IP rate limit at the AUTH tier — limits abuse
      attempts even by an attacker who *did* manage to step up.
    - Email confirmation echo + explicit irreversibility acknowledgement.
    - Single-transaction crypto-shred via :func:`purge_tenant`, which
      writes a real ``admin_audit_events`` row and returns its
      ``event_id`` so the certificate points at a verifiable audit row.
    """
    enforce_rate_limit(request, "dsar_erase", tier=TIER_AUTH, user_id=user_id)

    if not payload.acknowledge_irreversible:
        raise HTTPException(
            status_code=400,
            detail="Erasure requires explicit acknowledgement of irreversibility",
        )

    user = _user_row(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Subject not found")

    expected_email = str(user.get("email") or "").strip().lower()
    submitted = (payload.confirm_email or "").strip().lower()
    if not expected_email or submitted != expected_email:
        _emit_dsar_event(
            action="dsar_erase",
            user_id=user_id,
            request=request,
            outcome="denied",
            metadata={"reason": "email_mismatch"},
        )
        raise HTTPException(status_code=400, detail="Email confirmation did not match")

    # Pre-mint the certificate id so it lives inside the audit row's
    # metadata (proves the certificate the user holds matches the audit
    # trail) AND inside the security_audit_events emit below.
    certificate_id = str(uuid.uuid4())
    cert_issued_at = _now_iso()

    try:
        result = purge_tenant(
            user_id,
            actor_user_id=user_id,
            audit_metadata={
                "dsar_certificate_id": certificate_id,
                "dsar_certificate_issued_at": cert_issued_at,
            },
        )
    except Exception as exc:
        logger.exception("[dsar] erase failed for user_id=%s", user_id)
        _emit_dsar_event(
            action="dsar_erase",
            user_id=user_id,
            request=request,
            outcome="failure",
            metadata={"error": str(exc)[:200]},
        )
        raise HTTPException(status_code=500, detail="Erasure failed") from exc

    counts = result.get("counts", {}) if isinstance(result, dict) else {}
    raw_audit_id = result.get("admin_audit_event_id") if isinstance(result, dict) else None
    # Fail closed: a deletion certificate without a verifiable
    # admin_audit_events row is worthless for SOC 2 / HIPAA / GDPR
    # non-repudiation. If we cannot prove the audit row exists, abort
    # with a failure audit event instead of issuing a hollow cert.
    audit_event_id = ""
    if raw_audit_id:
        try:
            audit_event_id = str(uuid.UUID(str(raw_audit_id)))
        except (ValueError, TypeError):
            audit_event_id = ""
    if not audit_event_id:
        logger.error(
            "[dsar] erase aborted: purge_tenant did not return a valid admin_audit_event_id (user_id=%s)",
            user_id,
        )
        _emit_dsar_event(
            action="dsar_erase",
            user_id=user_id,
            request=request,
            outcome="failure",
            metadata={"error": "missing_admin_audit_event_id", "counts": counts},
        )
        raise HTTPException(
            status_code=500,
            detail="Erasure aborted: audit linkage missing",
        )
    certificate = _build_certificate(user_id, counts, audit_event_id)
    # Use the pre-minted id + issuance timestamp that purge_tenant
    # persisted into admin_audit_events.metadata. Pinning these fields
    # here means /erase/certificate retrieval returns immutable proof
    # material (certificate_id, completed_at, summary_sha256) — never a
    # newly minted "now()" — preserving non-repudiation semantics.
    certificate = certificate.model_copy(
        update={"certificate_id": certificate_id, "completed_at": cert_issued_at}
    )

    _emit_dsar_event(
        action="dsar_erase",
        user_id=user_id,
        request=request,
        outcome="success",
        metadata={
            "certificate_id": certificate.certificate_id,
            "summary_sha256": certificate.summary_sha256,
            "admin_audit_event_id": audit_event_id,
            "issued_at": cert_issued_at,
            "counts": counts,
        },
    )
    _record_workflow_row(
        request=request,
        request_type="erasure",
        user_id=user_id,
        audit_event_id=audit_event_id,
    )
    return certificate.model_dump()


@router.get("/erase/certificate")
async def dsar_get_erase_certificate(
    request: Request,
    certificate_id: str,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    """Retrieve a previously-issued deletion certificate by id.

    Look-up reads the ``admin_audit_events`` row written atomically by
    :func:`purge_tenant` (its metadata holds the ``dsar_certificate_id``
    we minted at /erase time). The DEK has already been crypto-shredded,
    so the only proof material that survives is exactly this audit row.

    Authorization model: only the original subject — or, in operator
    mode, an admin actor — may retrieve the cert. We match against
    ``actor_user_id`` / ``target_user_id`` so a subject who erased
    themselves can still pull their own proof, and an admin who actioned
    the erasure on behalf of a now-tombstoned subject can do the same.
    Rate-limited at the AUTH tier.
    """
    enforce_rate_limit(request, "dsar_certificate_lookup", tier=TIER_AUTH, user_id=user_id)
    try:
        cert_uuid = str(uuid.UUID(certificate_id))
    except (ValueError, TypeError):
        _emit_dsar_event(
            action="dsar_certificate_lookup",
            user_id=user_id,
            request=request,
            outcome="failure",
            metadata={"error": "invalid_certificate_id"},
        )
        raise HTTPException(status_code=400, detail="Invalid certificate id") from None

    if not get_database_url():
        raise HTTPException(status_code=503, detail="Datastore unavailable")

    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT event_id, actor_user_id, target_user_id,
                           created_at, metadata
                    FROM admin_audit_events
                    WHERE action = 'tenant_purge'
                      AND metadata ->> 'dsar_certificate_id' = %s
                    LIMIT 1
                    """,
                (cert_uuid,),
            )
            row = cur.fetchone()
    except Exception:
        logger.exception("[dsar] cert lookup failed for cert_id=%s", cert_uuid)
        _emit_dsar_event(
            action="dsar_certificate_lookup",
            user_id=user_id,
            request=request,
            outcome="failure",
            metadata={"error": "lookup_failed", "certificate_id": cert_uuid},
        )
        raise HTTPException(status_code=500, detail="Certificate lookup failed") from None

    if not row:
        _emit_dsar_event(
            action="dsar_certificate_lookup",
            user_id=user_id,
            request=request,
            outcome="failure",
            metadata={"error": "not_found", "certificate_id": cert_uuid},
        )
        raise HTTPException(status_code=404, detail="Certificate not found")

    if isinstance(row, dict):
        actor = str(row.get("actor_user_id") or "")
        target = str(row.get("target_user_id") or "")
        event_id = str(row.get("event_id") or "")
        metadata = row.get("metadata") or {}
    else:
        event_id, actor, target, _created_at, metadata = row
        actor, target, event_id = str(actor or ""), str(target or ""), str(event_id or "")
        metadata = metadata or {}

    if user_id not in {actor, target}:
        # Don't leak existence: 404 is the right answer for an
        # unauthorised lookup. Audit the denied access — auditors must
        # be able to see who tried to scrape someone else's cert.
        _emit_dsar_event(
            action="dsar_certificate_lookup",
            user_id=user_id,
            request=request,
            outcome="denied",
            metadata={"error": "unauthorized", "certificate_id": cert_uuid},
        )
        raise HTTPException(status_code=404, detail="Certificate not found")

    if isinstance(metadata, str):
        import json as _json_mod

        try:
            metadata = _json_mod.loads(metadata)
        except Exception:
            metadata = {}

    # Return *immutable persisted* certificate fields. The
    # ``dsar_certificate_issued_at`` value was written by purge_tenant
    # in the same transaction as the deletion — we never regenerate
    # ``completed_at`` at lookup time (that would weaken non-repudiation).
    # If the persisted issuance timestamp is missing the cert is
    # incomplete proof material → fail closed rather than return a
    # certificate with an empty ``completed_at``.
    issued_at = str((metadata or {}).get("dsar_certificate_issued_at") or "")
    if not issued_at:
        logger.error(
            "[dsar] cert lookup: persisted issued_at missing for cert_id=%s",
            cert_uuid,
        )
        _emit_dsar_event(
            action="dsar_certificate_lookup",
            user_id=user_id,
            request=request,
            outcome="failure",
            metadata={
                "error": "incomplete_proof_material",
                "certificate_id": cert_uuid,
                "admin_audit_event_id": event_id,
            },
        )
        raise HTTPException(status_code=500, detail="Certificate proof incomplete")
    counts = {
        k: v
        for k, v in (metadata or {}).items()
        if k not in {"dsar_certificate_id", "dsar_certificate_issued_at"}
        and isinstance(v, int | float)
    }
    summary = json.dumps(counts, sort_keys=True, default=str)
    digest = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    cert = DeletionCertificate(
        certificate_id=cert_uuid,
        user_id=target or actor,
        completed_at=issued_at,
        summary_sha256=digest,
        audit_event=event_id,
        counts=counts,
    )
    _emit_dsar_event(
        action="dsar_certificate_lookup",
        user_id=user_id,
        request=request,
        outcome="success",
        metadata={
            "certificate_id": cert_uuid,
            "admin_audit_event_id": event_id,
        },
    )
    return cert.model_dump()


@router.get("/retention/exceptions")
async def dsar_list_retention_exceptions(
    request: Request,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    """Auditor- and trust-center-facing view of the active retention
    exception register (legal holds, regulator investigations, etc.).
    Never reveals the internal SQL match predicate. Authenticated +
    AUTH-tier rate limited; the underlying register is also published
    on the trust center page."""
    enforce_rate_limit(request, "dsar_retention_exceptions", tier=TIER_AUTH, user_id=user_id)
    entries = retention_exceptions_public_view()
    _emit_dsar_event(
        action="dsar_retention_exceptions",
        user_id=user_id,
        request=request,
        outcome="success",
        metadata={"count": len(entries)},
    )
    return {
        "schema_version": "1.0",
        "retrieved_at": _now_iso(),
        "exceptions": entries,
    }


__all__ = ["router"]
