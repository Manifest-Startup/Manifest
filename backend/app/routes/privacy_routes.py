from uuid import uuid4

from app.services.privacy_consent_service import (
    get_effective_privacy_preferences,
    persist_privacy_preferences,
    set_privacy_cookies,
)
from app.services.privacy_jurisdiction import (
    _gpc_signal,
    resolve_default_consent_for,
)
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


class PrivacyConsentUpdate(BaseModel):
    analytics_enabled: bool = False
    communications_enabled: bool = False
    # Granular purposes (Task 15). Defaulting these to False keeps
    # existing clients backwards-compatible: a client that does not
    # send the new field is treated as not-yet-consented for that
    # purpose, which is the conservative GDPR/CCPA stance.
    marketing_enabled: bool = False
    ai_training_enabled: bool = False
    cookies_enabled: bool = False
    do_not_sell_or_share: bool = False
    source: str | None = None


class PrivacyConsentWithdraw(BaseModel):
    """Per-purpose withdrawal of consent (GDPR Art. 7(3)).

    The client lists the purposes to revoke. Anything omitted keeps its
    current value, so the user can withdraw a single purpose without
    losing the rest of their preferences. ``do_not_sell_or_share=true``
    is set whenever ``marketing_enabled`` or ``analytics_enabled`` is
    revoked, mirroring CPRA opt-out semantics.
    """

    purposes: list[str] = []
    reason: str | None = None


@router.get("/consent")
async def get_privacy_consent(request: Request, response: Response):
    preferences = get_effective_privacy_preferences(request)
    # Jurisdiction-aware defaults (GDPR / CCPA / GPC). When the visitor
    # has no stored preference we tell the client what *defaults* apply
    # in their region so the cookie banner can pre-select the right
    # boxes. When the visitor has expressed a Do-Not-Sell signal via
    # GPC, that always overrides the stored preference for the
    # do_not_sell_or_share field — GPC is treated as a real, in-band
    # opt-out per CPRA §7025.
    jurisdiction = resolve_default_consent_for(request)
    if not preferences.get("has_stored_preference"):
        # Fresh visitor / no stored preference — pre-fill the cookie
        # banner with the regional defaults.
        preferences["analytics_enabled"] = jurisdiction.analytics_enabled_default
        preferences["communications_enabled"] = jurisdiction.communications_enabled_default
        preferences["do_not_sell_or_share"] = jurisdiction.do_not_sell_or_share_default
    else:
        # Stored preference exists — never silently override it from a
        # *default*. The only legal override is an explicit Do-Not-Sell
        # signal in this very request: GPC (CPRA §7025). Without that
        # signal, granular opt-in/opt-out choices made in EU/US-privacy
        # regions are preserved verbatim so a user who deliberately
        # opted in to analytics from Germany is not flipped back off
        # on every read.
        if jurisdiction.honours_gpc and _gpc_signal(request):
            preferences["do_not_sell_or_share"] = True
    preferences["jurisdiction"] = jurisdiction.to_dict()

    if preferences.get("has_stored_preference"):
        analytics_visitor_id = None
        if preferences.get("analytics_enabled") and not preferences.get("do_not_sell_or_share"):
            analytics_visitor_id = request.cookies.get("visitor_id") or str(uuid4())
        set_privacy_cookies(
            response,
            preferences,
            privacy_visitor_id=request.cookies.get("manifest_privacy_visitor"),
            analytics_visitor_id=analytics_visitor_id,
        )
    return preferences


@router.post("/consent")
async def update_privacy_consent(
    request: Request, response: Response, payload: PrivacyConsentUpdate
):
    return persist_privacy_preferences(
        request,
        response,
        payload.model_dump(),
        source=payload.source or "settings",
    )


@router.post("/consent/withdraw")
async def withdraw_privacy_consent(
    request: Request, response: Response, payload: PrivacyConsentWithdraw
):
    """Withdraw consent for one or more purposes (GDPR Art. 7(3)).

    Withdrawal writes an immutable, append-only ledger row via
    :func:`persist_privacy_preferences` (the same write path used by
    /consent), tagged with ``source=consent_withdraw`` so audit can
    distinguish revocations from grants. Each withdrawal flips the
    listed purpose to False and emits a ``privacy_consent_withdrawn``
    audit event with the explicit purpose list and optional reason.
    """
    from app.services.privacy_consent_service import (
        GRANULAR_PURPOSES,
        get_effective_privacy_preferences,
    )
    from app.services.security_audit_service import record_security_event

    current = get_effective_privacy_preferences(request)
    valid = {p for p in payload.purposes if p in GRANULAR_PURPOSES}
    invalid = [p for p in payload.purposes if p not in GRANULAR_PURPOSES]
    next_state = {p: bool(current.get(p)) for p in GRANULAR_PURPOSES}
    for p in valid:
        next_state[p] = False
    # CPRA: opting out of analytics/marketing implies do-not-sell.
    if "analytics_enabled" in valid or "marketing_enabled" in valid:
        next_state["do_not_sell_or_share"] = True

    persisted = persist_privacy_preferences(
        request, response, next_state, source="consent_withdraw"
    )
    try:
        record_security_event(
            "privacy_consent_withdrawn",
            actor_type="user",
            action="privacy_consent_withdrawn",
            target_type="privacy_consent",
            outcome="success",
            metadata={
                "purposes_withdrawn": sorted(valid),
                "purposes_invalid": invalid,
                "reason": payload.reason,
            },
        )
    except Exception:  # pragma: no cover
        pass
    return {
        "withdrawn": sorted(valid),
        "ignored": invalid,
        "preferences": persisted,
    }
