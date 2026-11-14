from types import SimpleNamespace

from app.services.privacy_jurisdiction import resolve_default_consent_for


def _req(headers=None):
    return SimpleNamespace(headers=headers or {})


def test_gdpr_country_requires_optin_and_defaults_to_dns():
    profile = resolve_default_consent_for(_req({"cf-ipcountry": "DE"}))
    assert profile.requires_explicit_optin is True
    assert profile.do_not_sell_or_share_default is True
    assert profile.analytics_enabled_default is False
    assert profile.jurisdiction.startswith("GDPR:")


def test_uk_is_treated_as_gdpr():
    profile = resolve_default_consent_for(_req({"cf-ipcountry": "GB"}))
    assert profile.requires_explicit_optin is True
    assert "GB" in profile.jurisdiction


def test_global_privacy_control_signal_sets_do_not_sell():
    profile = resolve_default_consent_for(_req({"cf-ipcountry": "US", "sec-gpc": "1"}))
    assert profile.do_not_sell_or_share_default is True
    assert profile.honours_gpc is True


def test_default_row_is_conservative_but_not_optin():
    profile = resolve_default_consent_for(_req({"cf-ipcountry": "AU"}))
    assert profile.requires_explicit_optin is False
    assert profile.analytics_enabled_default is False
    assert profile.do_not_sell_or_share_default is False


def test_california_triggers_dns_default():
    profile = resolve_default_consent_for(
        _req({"cf-ipcountry": "US", "x-region": "CA", "sec-gpc": "1"})
    )
    assert profile.do_not_sell_or_share_default is True


def test_california_alone_triggers_state_privacy_law_defaults():
    """California (CCPA/CPRA) must opt-out-of-sale by default — no GPC
    header required."""
    profile = resolve_default_consent_for(
        _req({"cf-ipcountry": "US", "x-region": "CA"})
    )
    assert profile.do_not_sell_or_share_default is True
    assert profile.jurisdiction.endswith("US-CA")


def test_virginia_triggers_state_privacy_law_defaults():
    """VCDPA — Virginia must also default to do-not-sell-or-share."""
    profile = resolve_default_consent_for(
        _req({"cf-ipcountry": "US", "cf-region-code": "VA"})
    )
    assert profile.do_not_sell_or_share_default is True
    assert profile.jurisdiction.endswith("US-VA")


def test_us_state_without_privacy_law_does_not_force_dns_default():
    """A US state with no comprehensive privacy law (e.g. Florida)
    must NOT be treated as opt-out-of-sale — that would over-apply
    CCPA semantics. Past bug: code blanket-mapped US -> US-CA."""
    profile = resolve_default_consent_for(
        _req({"cf-ipcountry": "US", "x-region": "FL"})
    )
    assert profile.do_not_sell_or_share_default is False
    assert profile.requires_explicit_optin is False
    assert "US-CA" not in profile.jurisdiction


def test_us_with_no_state_signal_is_not_assumed_california():
    """Bare ``US`` with no state header must fall back to neutral
    defaults, not CCPA — we cannot legally guess California."""
    profile = resolve_default_consent_for(_req({"cf-ipcountry": "US"}))
    assert profile.do_not_sell_or_share_default is False
    assert "US-CA" not in profile.jurisdiction
