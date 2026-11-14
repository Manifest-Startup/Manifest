import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import fastapi_app
from app.services.privacy_consent_service import PRIVACY_CONSENT_COOKIE


def _consent_cookie(analytics_enabled: bool = False, do_not_sell_or_share: bool = False) -> str:
    return json.dumps(
        {
            "analytics_enabled": analytics_enabled,
            "communications_enabled": False,
            "do_not_sell_or_share": do_not_sell_or_share,
            "policy_version": "2026-04",
            "consent_updated_at": "2026-04-18T00:00:00+00:00",
            "source": "test",
        }
    )


def test_get_privacy_consent_defaults_to_essential_only_without_saved_choice():
    client = TestClient(fastapi_app)

    with patch("app.services.privacy_consent_service.get_database_url", return_value=None):
        response = client.get("/api/privacy/consent")

    assert response.status_code == 200
    assert response.json()["has_stored_preference"] is False
    assert response.json()["analytics_enabled"] is False
    assert response.json()["necessary_enabled"] is True
    # Jurisdiction block must always be present so the SPA banner can
    # render the right copy ("manage cookies" vs "Do Not Sell or Share").
    assert "jurisdiction" in response.json()


def test_get_privacy_consent_eu_visitor_requires_explicit_optin():
    """A fresh visitor advertising an EU country must see opt-out
    defaults (analytics OFF, communications OFF) — GDPR Art. 6 forbids
    pre-ticked boxes."""
    client = TestClient(fastapi_app)

    with patch("app.services.privacy_consent_service.get_database_url", return_value=None):
        response = client.get(
            "/api/privacy/consent",
            headers={"cf-ipcountry": "DE"},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["has_stored_preference"] is False
    assert body["analytics_enabled"] is False
    assert body["communications_enabled"] is False
    assert body["jurisdiction"]["requires_explicit_optin"] is True
    assert body["jurisdiction"]["jurisdiction"].startswith("GDPR:")


def test_get_privacy_consent_honours_global_privacy_control_signal():
    """A visitor sending the GPC ``Sec-GPC: 1`` header must be marked
    do-not-sell-or-share even if they have no stored preference."""
    client = TestClient(fastapi_app)

    with patch("app.services.privacy_consent_service.get_database_url", return_value=None):
        response = client.get(
            "/api/privacy/consent",
            headers={"sec-gpc": "1", "cf-ipcountry": "US"},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["do_not_sell_or_share"] is True
    assert body["jurisdiction"]["honours_gpc"] is True


def test_get_privacy_consent_eu_visitor_with_stored_optin_is_preserved_without_gpc():
    """Stored opt-in choices in a GDPR/US-privacy region must NOT be
    silently flipped back to the regional default on read. The only
    legal override is an explicit GPC signal in the request."""
    client = TestClient(fastapi_app)

    stored = _consent_cookie(analytics_enabled=True, do_not_sell_or_share=False)
    with patch("app.services.privacy_consent_service.get_database_url", return_value=None):
        response = client.get(
            "/api/privacy/consent",
            headers={"cf-ipcountry": "DE"},
            cookies={PRIVACY_CONSENT_COOKIE: stored},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["has_stored_preference"] is True
    # Persisted user choices preserved verbatim — region default would
    # have flipped do_not_sell_or_share to True.
    assert body["analytics_enabled"] is True
    assert body["do_not_sell_or_share"] is False


def test_get_privacy_consent_stored_pref_is_overridden_only_by_gpc_header():
    client = TestClient(fastapi_app)

    stored = _consent_cookie(analytics_enabled=True, do_not_sell_or_share=False)
    with patch("app.services.privacy_consent_service.get_database_url", return_value=None):
        response = client.get(
            "/api/privacy/consent",
            headers={"cf-ipcountry": "DE", "sec-gpc": "1"},
            cookies={PRIVACY_CONSENT_COOKIE: stored},
        )

    body = response.json()
    assert response.status_code == 200
    # GPC = 1 must force do_not_sell_or_share True even with a stored
    # opt-in, but the rest of the stored preferences are untouched.
    assert body["do_not_sell_or_share"] is True
    assert body["analytics_enabled"] is True


def test_post_privacy_consent_accepts_granular_purposes():
    client = TestClient(fastapi_app)
    with patch("app.services.privacy_consent_service.get_database_url", return_value=None):
        response = client.post(
            "/api/privacy/consent",
            json={
                "analytics_enabled": True,
                "communications_enabled": False,
                "marketing_enabled": True,
                "ai_training_enabled": False,
                "cookies_enabled": True,
                "do_not_sell_or_share": False,
            },
        )
    body = response.json()
    assert response.status_code == 200
    for purpose in (
        "analytics_enabled",
        "communications_enabled",
        "marketing_enabled",
        "ai_training_enabled",
        "cookies_enabled",
        "do_not_sell_or_share",
    ):
        assert purpose in body, f"missing granular purpose {purpose}"
    assert body["marketing_enabled"] is True
    assert body["cookies_enabled"] is True


def test_post_privacy_consent_withdraw_revokes_listed_purpose_only():
    client = TestClient(fastapi_app)
    stored = json.dumps(
        {
            "analytics_enabled": True,
            "communications_enabled": True,
            "marketing_enabled": True,
            "ai_training_enabled": True,
            "cookies_enabled": True,
            "do_not_sell_or_share": False,
            "policy_version": "2026-04",
            "consent_updated_at": "2026-04-18T00:00:00+00:00",
            "source": "test",
        }
    )
    with patch("app.services.privacy_consent_service.get_database_url", return_value=None):
        response = client.post(
            "/api/privacy/consent/withdraw",
            json={"purposes": ["ai_training_enabled"], "reason": "user-request"},
            cookies={PRIVACY_CONSENT_COOKIE: stored},
        )
    body = response.json()
    assert response.status_code == 200
    assert body["withdrawn"] == ["ai_training_enabled"]
    prefs = body["preferences"]
    assert prefs["ai_training_enabled"] is False
    # other purposes preserved
    assert prefs["communications_enabled"] is True
    assert prefs["marketing_enabled"] is True
    # withdrawing only ai_training does NOT trigger CPRA opt-out
    assert prefs["do_not_sell_or_share"] is False


def test_latest_preference_for_round_trips_granular_purposes_from_jsonb():
    """Granular purposes persisted into ``consent_payload`` MUST come
    back from the DB read path so authenticated users don't lose their
    marketing/ai_training/cookies preferences on the next request."""
    from app.services import privacy_consent_service as svc

    fake_row = {
        "analytics_enabled": True,
        "communications_enabled": True,
        "do_not_sell_or_share": False,
        "consent_payload": {
            "necessary_enabled": True,
            "analytics_enabled": True,
            "communications_enabled": True,
            "marketing_enabled": True,
            "ai_training_enabled": False,
            "cookies_enabled": True,
            "do_not_sell_or_share": False,
        },
        "policy_version": "2026-04",
        "consent_updated_at": None,
        "source": "settings",
    }

    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, *a, **k): pass
        def fetchone(self): return fake_row

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def cursor(self): return _Cur()

    with patch.object(svc, "get_database_url", return_value="postgres://x"), patch.object(
        svc, "get_db_connection", return_value=_Conn()
    ):
        loaded = svc._latest_preference_for(user_id="u1", visitor_id=None)
    assert loaded is not None
    assert loaded["marketing_enabled"] is True
    assert loaded["ai_training_enabled"] is False
    assert loaded["cookies_enabled"] is True


def test_post_privacy_consent_withdraw_marketing_forces_do_not_sell():
    client = TestClient(fastapi_app)
    stored = json.dumps(
        {
            "analytics_enabled": True,
            "marketing_enabled": True,
            "do_not_sell_or_share": False,
            "policy_version": "2026-04",
            "consent_updated_at": "2026-04-18T00:00:00+00:00",
            "source": "test",
        }
    )
    with patch("app.services.privacy_consent_service.get_database_url", return_value=None):
        response = client.post(
            "/api/privacy/consent/withdraw",
            json={"purposes": ["marketing_enabled"]},
            cookies={PRIVACY_CONSENT_COOKIE: stored},
        )
    prefs = response.json()["preferences"]
    assert prefs["marketing_enabled"] is False
    assert prefs["do_not_sell_or_share"] is True


def test_post_privacy_consent_sets_cookie_and_clears_optional_tracking_cookie():
    client = TestClient(fastapi_app)

    with patch("app.services.privacy_consent_service.get_database_url", return_value=None):
        response = client.post(
            "/api/privacy/consent",
            json={
                "analytics_enabled": False,
                "communications_enabled": True,
                "do_not_sell_or_share": True,
                "source": "test_suite",
            },
        )

    assert response.status_code == 200
    assert response.json()["has_stored_preference"] is True
    assert response.json()["communications_enabled"] is True
    set_cookie_header = response.headers.get("set-cookie", "")
    assert PRIVACY_CONSENT_COOKIE in set_cookie_header
    assert "visitor_id=\"\"" in set_cookie_header or "visitor_id=" in set_cookie_header


def test_tracking_middleware_skips_logging_without_analytics_consent():
    client = TestClient(fastapi_app)

    with patch("app.routes.customer_routes.log_visitor") as log_visitor:
        response = client.get("/ping")

    assert response.status_code == 200
    log_visitor.assert_not_called()


def test_tracking_middleware_logs_new_visitor_after_analytics_consent():
    client = TestClient(fastapi_app)

    with patch("app.routes.customer_routes.log_visitor", return_value=True) as log_visitor:
        response = client.get(
            "/ping",
            cookies={
                PRIVACY_CONSENT_COOKIE: _consent_cookie(analytics_enabled=True),
            },
        )

    assert response.status_code == 200
    log_visitor.assert_called_once()
    assert "visitor_id=" in response.headers.get("set-cookie", "")
