"""
Jurisdiction-aware default privacy preferences.

GDPR (EEA, UK, Switzerland) requires opt-in for non-essential cookies
and most analytics. CCPA/CPRA (California) honours a Do-Not-Sell signal
and the Global Privacy Control (GPC) header. For other regions we keep
the existing opt-in default for analytics and only honour communications
when the user explicitly enables them.

This module is deliberately small and pure: it resolves a request to a
``DefaultConsentProfile`` so the cookie banner / consent middleware can
seed defaults correctly without ever calling out to a paid geo-IP feed.
We use the request's country header (``cf-ipcountry`` or ``x-country``,
both standard at our edge) and the GPC header.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

# ISO 3166-1 alpha-2 country codes that fall under GDPR (EEA + UK + CH).
GDPR_COUNTRIES: set[str] = {
    "AT",
    "BE",
    "BG",
    "HR",
    "CY",
    "CZ",
    "DK",
    "EE",
    "FI",
    "FR",
    "DE",
    "GR",
    "HU",
    "IE",
    "IT",
    "LV",
    "LT",
    "LU",
    "MT",
    "NL",
    "PL",
    "PT",
    "RO",
    "SK",
    "SI",
    "ES",
    "SE",  # EU
    "IS",
    "LI",
    "NO",  # EEA non-EU
    "GB",
    "CH",  # UK + Switzerland
}

CCPA_REGIONS: set[str] = {"US-CA"}

# US states that have shipped CCPA-equivalent consumer-privacy laws
# (CPRA, VCDPA, CPA, CTDPA, UCPA, ...). Treated as opt-out-of-sale
# regimes — same defaults as CCPA, but labelled by state.
US_STATE_PRIVACY_LAWS: set[str] = {
    "CA",  # CCPA / CPRA
    "VA",  # VCDPA
    "CO",  # CPA
    "CT",  # CTDPA
    "UT",  # UCPA
    "TX",  # TDPSA
    "OR",  # OCPA
    "MT",  # MCDPA
}


@dataclass(frozen=True)
class DefaultConsentProfile:
    """The default consent stance for a fresh visitor in a given region."""

    jurisdiction: str
    analytics_enabled_default: bool
    communications_enabled_default: bool
    do_not_sell_or_share_default: bool
    requires_explicit_optin: bool
    honours_gpc: bool

    def to_dict(self) -> dict:
        return {
            "jurisdiction": self.jurisdiction,
            "analytics_enabled": self.analytics_enabled_default,
            "communications_enabled": self.communications_enabled_default,
            "do_not_sell_or_share": self.do_not_sell_or_share_default,
            "requires_explicit_optin": self.requires_explicit_optin,
            "honours_gpc": self.honours_gpc,
        }


def _country_from_request(request: Request) -> str | None:
    headers = request.headers
    return (
        headers.get("cf-ipcountry")
        or headers.get("x-country")
        or headers.get("x-vercel-ip-country")
        or None
    )


def _us_state_from_request(request: Request) -> str | None:
    """Extract a US state code (e.g. ``CA``, ``VA``) from any of the
    common geo headers our edge sets. We *never* assume California for
    a bare ``US`` country signal — that would over-apply CCPA defaults
    to non-CCPA states and under-apply VCDPA/CPA/etc. to states that
    have their own laws.
    """
    headers = request.headers
    raw = (
        headers.get("cf-region-code")
        or headers.get("cf-region")
        or headers.get("x-vercel-ip-country-region")
        or headers.get("x-region")
        or ""
    )
    raw = str(raw).strip().upper()
    # Some providers send the full name ("CALIFORNIA"); we only trust
    # 2-letter ISO state codes.
    if len(raw) == 2 and raw.isalpha():
        return raw
    return None


def _gpc_signal(request: Request) -> bool:
    """RFC-pending Global Privacy Control header. Treat any "1" / "true"
    as a do-not-sell signal."""
    raw = request.headers.get("sec-gpc") or request.headers.get("dnt")
    return str(raw or "").strip().lower() in {"1", "true", "yes"}


def resolve_default_consent_for(request: Request) -> DefaultConsentProfile:
    """Resolve the default consent stance for an incoming request.

    Decision matrix:
    - GDPR region              -> all non-essential default OFF, opt-in required
    - CCPA region OR GPC=1     -> do-not-sell defaults ON
    - everywhere else          -> conservative defaults (analytics OFF,
                                  communications OFF, dns OFF) but no
                                  hard opt-in requirement
    """
    country = (_country_from_request(request) or "").upper()
    gpc = _gpc_signal(request)

    if country in GDPR_COUNTRIES:
        return DefaultConsentProfile(
            jurisdiction=f"GDPR:{country}",
            analytics_enabled_default=False,
            communications_enabled_default=False,
            do_not_sell_or_share_default=True,
            requires_explicit_optin=True,
            honours_gpc=True,
        )

    state = _us_state_from_request(request) if country == "US" else None
    if state and state in US_STATE_PRIVACY_LAWS:
        return DefaultConsentProfile(
            jurisdiction=f"US-PRIVACY:US-{state}",
            analytics_enabled_default=False,
            communications_enabled_default=False,
            do_not_sell_or_share_default=True,
            requires_explicit_optin=False,
            honours_gpc=True,
        )
    if gpc:
        return DefaultConsentProfile(
            jurisdiction="GPC",
            analytics_enabled_default=False,
            communications_enabled_default=False,
            do_not_sell_or_share_default=True,
            requires_explicit_optin=False,
            honours_gpc=True,
        )

    return DefaultConsentProfile(
        jurisdiction=(f"US-{state}" if (country == "US" and state) else (country or "ROW")),
        analytics_enabled_default=False,
        communications_enabled_default=False,
        do_not_sell_or_share_default=False,
        requires_explicit_optin=False,
        honours_gpc=True,
    )


__all__ = [
    "DefaultConsentProfile",
    "GDPR_COUNTRIES",
    "CCPA_REGIONS",
    "resolve_default_consent_for",
]
