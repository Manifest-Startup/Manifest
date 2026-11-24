"""Tests for DSAR endpoints (Task #15 — Privacy & Compliance)."""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import fastapi_app
from app.routes.dsar_routes import (
    _build_certificate,
    _collect_subject_data,
)


USER_ID = "00000000-0000-0000-0000-000000000123"


@pytest.fixture
def auth_client():
    """Authenticated test client.

    Overrides ``require_user_id`` and stubs ``_recent_login_satisfies``
    to True so dependencies that gate on ``require_recent_auth`` (DSAR
    /erase, /rectify) accept the request as if the caller had just
    re-authenticated.
    """
    client = TestClient(fastapi_app)
    fastapi_app.dependency_overrides = getattr(fastapi_app, "dependency_overrides", {})
    from app.routes.dependencies import require_user_id

    fastapi_app.dependency_overrides[require_user_id] = lambda: USER_ID
    # Disable the DB-backed rate limiter for the happy-path fixture so
    # accumulated bucket entries from prior tests don't cause spurious
    # 429s. The dedicated rate-limit test patches `enforce_rate_limit`
    # itself to assert the 429 path.
    with patch(
        "app.security.step_up._recent_login_satisfies", return_value=True
    ), patch(
        "app.services.shared.rate_limit.rate_limit_service.allow",
        return_value=True,
    ):
        yield client
    fastapi_app.dependency_overrides.pop(require_user_id, None)


@pytest.fixture
def unauth_client():
    """Client with no auth override — exercises the un-authenticated path."""
    return TestClient(fastapi_app)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_collect_subject_data_returns_envelope_with_categories():
    fake_user = {"user_id": USER_ID, "email": "u@example.com"}
    with patch(
        "app.routes.dsar_routes._fetchall_required",
        side_effect=lambda *a, **k: [fake_user] if "FROM users" in a[0] else [],
    ), patch("app.routes.dsar_routes._fetchall_safe", return_value=[]):
        envelope = _collect_subject_data(USER_ID)

    assert envelope["schema_version"] == "1.0"
    assert envelope["subject"]["user_id"] == USER_ID
    assert envelope["subject"]["profile"] == fake_user
    assert envelope["partial"] is False
    assert envelope["errors"] == {}
    for required in (
        "sessions",
        "mfa_factors",
        "webauthn_credentials",
        "privacy_consents",
        "integrations",
        "api_keys",
        "vault_files",
        "goals",
        "goal_steps",
        "approvals",
        "knowledge_facts",
        "goal_events",
    ):
        assert required in envelope["categories"]


def test_collect_subject_data_partial_on_optional_failure():
    """Optional category errors surface as partial=true + errors map,
    they do NOT raise — but the route MUST audit outcome=partial."""
    fake_user = {"user_id": USER_ID, "email": "u@example.com"}
    def safe_side_effect(*a, **k):
        # Simulate one optional category failing.
        if k.get("label") == "integrations":
            errors = k.get("errors")
            if errors is not None:
                errors["integrations"] = "permission denied"
            return []
        return []
    with patch(
        "app.routes.dsar_routes._fetchall_required",
        side_effect=lambda *a, **k: [fake_user] if "FROM users" in a[0] else [],
    ), patch(
        "app.routes.dsar_routes._fetchall_safe",
        side_effect=safe_side_effect,
    ):
        envelope = _collect_subject_data(USER_ID)
    assert envelope["partial"] is True
    assert "integrations" in envelope["errors"]


def test_collect_subject_data_required_failure_raises():
    """If a required category errors, _collect_subject_data MUST raise
    DSARDataExtractionError so the route can fail closed (503)."""
    from app.routes.dsar_routes import DSARDataExtractionError

    def required_raise(*a, **k):
        raise DSARDataExtractionError(f"{k.get('label')}:boom")

    with patch(
        "app.routes.dsar_routes._fetchall_required", side_effect=required_raise
    ), patch("app.routes.dsar_routes._fetchall_safe", return_value=[]):
        with pytest.raises(DSARDataExtractionError):
            _collect_subject_data(USER_ID)


def test_access_fails_closed_on_required_data_failure(auth_client):
    """A DB outage on a required category MUST surface as 503 + a
    failure audit event, NOT 200 with empty payload."""
    from app.routes.dsar_routes import DSARDataExtractionError

    with patch(
        "app.routes.dsar_routes._collect_subject_data",
        side_effect=DSARDataExtractionError("profile:db_down"),
    ), patch("app.routes.dsar_routes.record_security_event") as audit, patch(
        "app.routes.dsar_routes._record_workflow_row"
    ):
        resp = auth_client.get("/api/dsar/access")
    assert resp.status_code == 503
    assert audit.call_args.kwargs["outcome"] == "failure"
    assert audit.call_args.kwargs["action"] == "dsar_access"


def test_access_audits_partial_outcome_when_optional_category_fails(auth_client):
    fake_user = {"user_id": USER_ID, "email": "u@example.com"}
    def safe_side_effect(*a, **k):
        if k.get("label") == "api_keys":
            errors = k.get("errors")
            if errors is not None:
                errors["api_keys"] = "boom"
        return []
    with patch(
        "app.routes.dsar_routes._fetchall_required",
        side_effect=lambda *a, **k: [fake_user] if "FROM users" in a[0] else [],
    ), patch(
        "app.routes.dsar_routes._fetchall_safe", side_effect=safe_side_effect
    ), patch("app.routes.dsar_routes.record_security_event") as audit, patch(
        "app.routes.dsar_routes._record_workflow_row"
    ):
        resp = auth_client.get("/api/dsar/access")
    assert resp.status_code == 200
    body = resp.json()
    assert body["partial"] is True
    assert "api_keys" in body["errors"]
    assert audit.call_args.kwargs["outcome"] == "partial"


def test_build_certificate_hashes_counts_deterministically():
    counts = {"users_tombstoned": 1, "user_sessions": 3}
    cert_a = _build_certificate(USER_ID, counts, "audit-1")
    cert_b = _build_certificate(USER_ID, counts, "audit-1")
    assert cert_a.summary_sha256 == cert_b.summary_sha256
    assert cert_a.method == "crypto_shred+hard_delete"
    assert cert_a.user_id == USER_ID


# ---------------------------------------------------------------------------
# Route smoke tests (auth dependency overridden)
# ---------------------------------------------------------------------------


def test_access_returns_envelope_and_emits_audit(auth_client):
    with patch(
        "app.routes.dsar_routes._fetchall_required", return_value=[]
    ), patch(
        "app.routes.dsar_routes._fetchall_safe", return_value=[]
    ), patch("app.routes.dsar_routes.record_security_event") as audit, patch(
        "app.routes.dsar_routes._record_workflow_row"
    ):
        resp = auth_client.get("/api/dsar/access")
    assert resp.status_code == 200
    body = resp.json()
    assert body["subject"]["user_id"] == USER_ID
    audit.assert_called_once()
    args, kwargs = audit.call_args
    assert args[0] == "dsar_request"
    assert kwargs["action"] == "dsar_access"
    assert kwargs["outcome"] == "success"


def test_portability_advertises_format(auth_client):
    with patch(
        "app.routes.dsar_routes._fetchall_required", return_value=[]
    ), patch(
        "app.routes.dsar_routes._fetchall_safe", return_value=[]
    ), patch(
        "app.routes.dsar_routes.record_security_event"
    ), patch(
        "app.routes.dsar_routes._record_workflow_row"
    ):
        resp = auth_client.get("/api/dsar/portability")
    assert resp.status_code == 200
    assert resp.json()["format"].startswith("application/json")


def test_object_persists_consent_and_audits(auth_client):
    captured: Dict[str, Any] = {}

    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return _Cur()
        def commit(self): captured["committed"] = True

    with patch("app.routes.dsar_routes.get_database_url", return_value="postgres://x"), \
         patch("app.routes.dsar_routes.get_db_connection", return_value=_Conn()), \
         patch("app.routes.dsar_routes.record_security_event") as audit:
        resp = auth_client.post(
            "/api/dsar/object",
            json={
                "analytics_enabled": False,
                "communications_enabled": False,
                "do_not_sell_or_share": True,
                "reason": "I object",
            },
        )

    assert resp.status_code == 200
    assert captured.get("committed") is True
    assert "INSERT INTO privacy_consents" in captured["sql"]
    assert audit.call_args.kwargs["action"] == "dsar_object"
    assert audit.call_args.kwargs["outcome"] == "success"


def test_rectify_requires_at_least_one_field(auth_client):
    resp = auth_client.post("/api/dsar/rectify", json={})
    assert resp.status_code == 400


def test_erase_requires_irreversible_ack(auth_client):
    resp = auth_client.post(
        "/api/dsar/erase",
        json={"confirm_email": "x@example.com", "acknowledge_irreversible": False},
    )
    assert resp.status_code == 400


def test_erase_rejects_email_mismatch(auth_client):
    with patch(
        "app.routes.dsar_routes._user_row",
        return_value={"user_id": USER_ID, "email": "real@example.com"},
    ), patch("app.routes.dsar_routes.record_security_event") as audit:
        resp = auth_client.post(
            "/api/dsar/erase",
            json={
                "confirm_email": "wrong@example.com",
                "acknowledge_irreversible": True,
            },
        )
    assert resp.status_code == 400
    audit.assert_called_once()
    assert audit.call_args.kwargs["outcome"] == "denied"


def test_erase_calls_purge_and_returns_certificate(auth_client):
    purge_counts = {"crypto_shredded": 1, "users_tombstoned": 1}
    real_audit_id = "11111111-2222-3333-4444-555555555555"
    purge_result = {
        "counts": purge_counts,
        "admin_audit_event_id": real_audit_id,
    }
    with patch(
        "app.routes.dsar_routes._user_row",
        return_value={"user_id": USER_ID, "email": "real@example.com"},
    ), patch(
        "app.routes.dsar_routes.purge_tenant", return_value=purge_result
    ) as purge, patch("app.routes.dsar_routes.record_security_event") as audit:
        resp = auth_client.post(
            "/api/dsar/erase",
            json={
                "confirm_email": "real@example.com",
                "acknowledge_irreversible": True,
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"] == purge_counts
    assert body["method"] == "crypto_shred+hard_delete"
    assert len(body["summary_sha256"]) == 64
    # The certificate's audit_event MUST be the real persisted event id
    # so the certificate is verifiable against the audit trail.
    assert body["audit_event"] == real_audit_id
    # purge_tenant must be invoked with the certificate id as audit
    # metadata so the audit row can be matched back to the cert.
    call_kwargs = purge.call_args.kwargs
    assert call_kwargs["actor_user_id"] == USER_ID
    assert call_kwargs["audit_metadata"]["dsar_certificate_id"] == body["certificate_id"]
    erase_audit = next(
        call
        for call in audit.call_args_list
        if call.kwargs.get("action") == "dsar_erase"
        and call.kwargs.get("outcome") == "success"
    )
    assert erase_audit.kwargs["metadata"]["admin_audit_event_id"] == real_audit_id


def test_erase_fails_closed_on_malformed_audit_event_id(auth_client):
    """A non-UUID audit id is just as un-verifiable as a missing one —
    treat both as fatal."""
    purge_result = {"counts": {"users_tombstoned": 1}, "admin_audit_event_id": "not-a-uuid"}
    with patch(
        "app.routes.dsar_routes._user_row",
        return_value={"user_id": USER_ID, "email": "real@example.com"},
    ), patch(
        "app.routes.dsar_routes.purge_tenant", return_value=purge_result
    ), patch("app.routes.dsar_routes.record_security_event") as audit:
        resp = auth_client.post(
            "/api/dsar/erase",
            json={
                "confirm_email": "real@example.com",
                "acknowledge_irreversible": True,
            },
        )
    assert resp.status_code == 500
    assert audit.call_args.kwargs["outcome"] == "failure"
    assert audit.call_args.kwargs["metadata"]["error"] == "missing_admin_audit_event_id"


def test_erase_fails_closed_when_audit_event_id_missing(auth_client):
    """If the purge primitive cannot return a verifiable admin audit
    row id, /erase MUST refuse to issue a deletion certificate. Issuing
    a certificate that cannot be matched against the audit trail
    breaks SOC 2 / HIPAA / GDPR non-repudiation."""
    purge_result = {"counts": {"users_tombstoned": 1}, "admin_audit_event_id": None}
    with patch(
        "app.routes.dsar_routes._user_row",
        return_value={"user_id": USER_ID, "email": "real@example.com"},
    ), patch(
        "app.routes.dsar_routes.purge_tenant", return_value=purge_result
    ), patch("app.routes.dsar_routes.record_security_event") as audit:
        resp = auth_client.post(
            "/api/dsar/erase",
            json={
                "confirm_email": "real@example.com",
                "acknowledge_irreversible": True,
            },
        )
    assert resp.status_code == 500
    assert audit.call_args.kwargs["outcome"] == "failure"
    assert audit.call_args.kwargs["metadata"]["error"] == "missing_admin_audit_event_id"


def test_erase_unauthenticated_is_rejected(unauth_client):
    resp = unauth_client.post(
        "/api/dsar/erase",
        json={
            "confirm_email": "real@example.com",
            "acknowledge_irreversible": True,
        },
    )
    assert resp.status_code == 401


def test_erase_without_recent_auth_returns_step_up_required():
    """When the session has no recent re-auth proof, /erase must 401
    with ``X-Step-Up-Required: 1`` so the SPA can prompt for a fresh
    proof of identity before destructive action."""
    client = TestClient(fastapi_app)
    fastapi_app.dependency_overrides = getattr(fastapi_app, "dependency_overrides", {})
    from app.routes.dependencies import require_user_id

    fastapi_app.dependency_overrides[require_user_id] = lambda: USER_ID
    try:
        with patch(
            "app.security.step_up._recent_login_satisfies", return_value=False
        ), patch(
            "app.security.step_up.has_recent_step_up", return_value=False
        ), patch(
            "app.security.step_up.get_current_session_id_optional",
            return_value=None,
        ):
            resp = client.post(
                "/api/dsar/erase",
                json={
                    "confirm_email": "real@example.com",
                    "acknowledge_irreversible": True,
                },
            )
    finally:
        fastapi_app.dependency_overrides.pop(require_user_id, None)
    assert resp.status_code == 401
    assert resp.headers.get("X-Step-Up-Required") == "1"


def test_erase_rate_limit_returns_429(auth_client):
    """When the AUTH-tier rate limit is exhausted, /erase must 429."""
    from fastapi import HTTPException, status

    def _blow_up(*_args, **_kwargs):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limited", "scope": "dsar_erase"},
            headers={"Retry-After": "900"},
        )

    with patch("app.routes.dsar_routes.enforce_rate_limit", side_effect=_blow_up):
        resp = auth_client.post(
            "/api/dsar/erase",
            json={
                "confirm_email": "real@example.com",
                "acknowledge_irreversible": True,
            },
        )
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "900"


def test_access_unauthenticated_is_rejected(unauth_client):
    resp = unauth_client.get("/api/dsar/access")
    assert resp.status_code == 401


def test_access_rate_limit_returns_429(auth_client):
    """GET /access must enforce AUTH-tier rate limiting to prevent
    envelope-scraping by an attacker with a stolen session cookie."""
    from fastapi import HTTPException, status

    def _blow_up(*_args, **_kwargs):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limited", "scope": "dsar_access"},
            headers={"Retry-After": "900"},
        )

    with patch("app.routes.dsar_routes.enforce_rate_limit", side_effect=_blow_up):
        resp = auth_client.get("/api/dsar/access")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "900"


def test_portability_rate_limit_returns_429(auth_client):
    from fastapi import HTTPException, status

    def _blow_up(*_args, **_kwargs):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limited", "scope": "dsar_portability"},
            headers={"Retry-After": "900"},
        )

    with patch("app.routes.dsar_routes.enforce_rate_limit", side_effect=_blow_up):
        resp = auth_client.get("/api/dsar/portability")
    assert resp.status_code == 429


def test_get_erase_certificate_returns_persisted_cert(auth_client):
    """The certificate retrieval endpoint must return the *immutable*
    persisted certificate fields written at /erase time (in particular
    the original ``completed_at`` / ``dsar_certificate_issued_at``),
    never regenerate them."""
    cert_id = "11111111-2222-3333-4444-555555555555"
    audit_event_id = "99999999-aaaa-bbbb-cccc-dddddddddddd"
    issued_at = "2026-04-01T12:34:56+00:00"

    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params):
            self._sql, self._params = sql, params
        def fetchone(self):
            return {
                "event_id": audit_event_id,
                "actor_user_id": USER_ID,
                "target_user_id": USER_ID,
                "created_at": "2026-04-19T00:00:00+00:00",
                "metadata": {
                    "dsar_certificate_id": cert_id,
                    "dsar_certificate_issued_at": issued_at,
                    "users_tombstoned": 1,
                    "crypto_shredded": 1,
                },
            }

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return _Cur()

    with patch("app.routes.dsar_routes.get_database_url", return_value="postgres://x"), \
         patch("app.routes.dsar_routes.get_db_connection", return_value=_Conn()), \
         patch("app.routes.dsar_routes._emit_dsar_event") as emit:
        resp = auth_client.get(f"/api/dsar/erase/certificate?certificate_id={cert_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["certificate_id"] == cert_id
    assert body["audit_event"] == audit_event_id
    assert body["method"] == "crypto_shred+hard_delete"
    # Immutability guarantee: completed_at must be the persisted issuance
    # timestamp, not a freshly regenerated "now()".
    assert body["completed_at"] == issued_at
    # And the lookup itself must be audited (success outcome).
    emit.assert_called_once()
    assert emit.call_args.kwargs["outcome"] == "success"
    assert emit.call_args.kwargs["action"] == "dsar_certificate_lookup"


def test_get_erase_certificate_fails_closed_when_issued_at_missing(auth_client):
    """If the persisted audit row lacks ``dsar_certificate_issued_at``
    the proof material is incomplete and we MUST fail closed rather
    than return a certificate with an empty completed_at."""
    cert_id = "44444444-4444-4444-4444-444444444444"

    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a, **k): pass
        def fetchone(self):
            return {
                "event_id": "77777777-7777-7777-7777-777777777777",
                "actor_user_id": USER_ID,
                "target_user_id": USER_ID,
                "created_at": "2026-04-19T00:00:00+00:00",
                # NOTE: dsar_certificate_issued_at intentionally absent.
                "metadata": {"dsar_certificate_id": cert_id, "users_tombstoned": 1},
            }

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return _Cur()

    with patch("app.routes.dsar_routes.get_database_url", return_value="postgres://x"), \
         patch("app.routes.dsar_routes.get_db_connection", return_value=_Conn()), \
         patch("app.routes.dsar_routes._emit_dsar_event") as emit:
        resp = auth_client.get(f"/api/dsar/erase/certificate?certificate_id={cert_id}")
    assert resp.status_code == 500
    emit.assert_called_once()
    assert emit.call_args.kwargs["outcome"] == "failure"
    assert emit.call_args.kwargs["metadata"]["error"] == "incomplete_proof_material"


def test_get_erase_certificate_unknown_id_returns_404(auth_client):
    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a, **k): pass
        def fetchone(self): return None

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return _Cur()

    with patch("app.routes.dsar_routes.get_database_url", return_value="postgres://x"), \
         patch("app.routes.dsar_routes.get_db_connection", return_value=_Conn()):
        resp = auth_client.get(
            "/api/dsar/erase/certificate?certificate_id=22222222-2222-2222-2222-222222222222"
        )
    assert resp.status_code == 404


def test_get_erase_certificate_unauthorized_subject_gets_404(auth_client):
    """A user who is neither actor nor target on the audit row must NOT
    be told the certificate exists — return 404, not 403."""
    cert_id = "33333333-3333-3333-3333-333333333333"

    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a, **k): pass
        def fetchone(self):
            return {
                "event_id": "88888888-8888-8888-8888-888888888888",
                "actor_user_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                "target_user_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                "created_at": "2026-04-19T00:00:00+00:00",
                "metadata": {"dsar_certificate_id": cert_id},
            }

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return _Cur()

    with patch("app.routes.dsar_routes.get_database_url", return_value="postgres://x"), \
         patch("app.routes.dsar_routes.get_db_connection", return_value=_Conn()), \
         patch("app.routes.dsar_routes._emit_dsar_event") as emit:
        resp = auth_client.get(f"/api/dsar/erase/certificate?certificate_id={cert_id}")
    assert resp.status_code == 404
    # Denied access by an unauthorised subject must still be audited.
    emit.assert_called_once()
    assert emit.call_args.kwargs["outcome"] == "denied"


def test_get_erase_certificate_rejects_malformed_id(auth_client):
    resp = auth_client.get("/api/dsar/erase/certificate?certificate_id=not-a-uuid")
    assert resp.status_code == 400


def test_retention_exceptions_endpoint_returns_register(auth_client):
    """The auditor-facing register endpoint must return the public
    view (no SQL match predicate) and never 500 on an empty file."""
    fake_entries = [
        {
            "id": "LIT-2026-001",
            "scope": "users",
            "reason": "Active litigation hold",
            "approved_by": "DPO",
            "opened_at": "2026-04-01T00:00:00Z",
            "ticket": "LEGAL-218",
        }
    ]
    with patch(
        "app.routes.dsar_routes.retention_exceptions_public_view",
        return_value=fake_entries,
    ):
        resp = auth_client.get("/api/dsar/retention/exceptions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["exceptions"] == fake_entries
    # The endpoint MUST never leak the SQL match predicate.
    for entry in body["exceptions"]:
        assert "match" not in entry


def test_erase_failure_emits_failure_audit(auth_client):
    with patch(
        "app.routes.dsar_routes._user_row",
        return_value={"user_id": USER_ID, "email": "real@example.com"},
    ), patch(
        "app.routes.dsar_routes.purge_tenant", side_effect=RuntimeError("boom")
    ), patch("app.routes.dsar_routes.record_security_event") as audit:
        resp = auth_client.post(
            "/api/dsar/erase",
            json={
                "confirm_email": "real@example.com",
                "acknowledge_irreversible": True,
            },
        )
    assert resp.status_code == 500
    assert audit.call_args.kwargs["outcome"] == "failure"
