"""Tests for the internal DSAR admin workflow + breach-timer surface
(Task #15 — operationalisation gaps flagged by validator).

Covers:
- ``dsar_workflow_service`` SLA-day mapping (CCPA 45d / default 30d) and
  state-machine validation.
- ``breach_timer_service`` deadline math (GDPR 72h / HIPAA 60d) and kind
  validation.
- ``/api/admin/dsar/*`` and ``/api/admin/incidents/breach-timers/*``
  routes are gated by :func:`require_admin` (non-admin → 403, admin
  reaches the service layer).
- The deadline-checker script emits the right audit event types for
  warning vs breached deadlines.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import fastapi_app
from app.services import breach_timer_service, dsar_workflow_service
from app.security.permissions import Principal


ADMIN_ID = "00000000-0000-0000-0000-0000000000aa"
USER_ID = "00000000-0000-0000-0000-0000000000bb"


def _admin_principal() -> Principal:
    return Principal(user_id=ADMIN_ID, role="admin", is_admin=True)


def _user_principal() -> Principal:
    return Principal(user_id=USER_ID, role="user", is_admin=False)


@pytest.fixture
def admin_client():
    client = TestClient(fastapi_app)
    from app.routes.dependencies import require_user_id
    from app.security.permissions import get_principal

    fastapi_app.dependency_overrides[require_user_id] = lambda: ADMIN_ID
    fastapi_app.dependency_overrides[get_principal] = _admin_principal
    with patch(
        "app.services.rate_limit_service.rate_limit_service.allow",
        return_value=True,
    ), patch(
        "app.security.permissions.get_user_mfa_status",
        return_value={"enabled": True},
        create=True,
    ), patch(
        "app.services.totp_mfa_service.get_user_mfa_status",
        return_value={"enabled": True},
    ):
        yield client
    fastapi_app.dependency_overrides.pop(require_user_id, None)
    fastapi_app.dependency_overrides.pop(get_principal, None)


@pytest.fixture
def nonadmin_client():
    client = TestClient(fastapi_app)
    from app.routes.dependencies import require_user_id
    from app.security.permissions import get_principal

    fastapi_app.dependency_overrides[require_user_id] = lambda: USER_ID
    fastapi_app.dependency_overrides[get_principal] = _user_principal
    with patch(
        "app.services.rate_limit_service.rate_limit_service.allow",
        return_value=True,
    ):
        yield client
    fastapi_app.dependency_overrides.pop(require_user_id, None)
    fastapi_app.dependency_overrides.pop(get_principal, None)


# ---------------------------------------------------------------------------
# Pure service-layer behaviour
# ---------------------------------------------------------------------------


def test_dsar_sla_days_defaults_to_gdpr_30():
    assert dsar_workflow_service._sla_days_for(None) == dsar_workflow_service.DEFAULT_SLA_DAYS
    assert dsar_workflow_service._sla_days_for("EU-DE") == 30


def test_dsar_sla_days_for_california_is_ccpa_45():
    assert dsar_workflow_service._sla_days_for("US-CA") == dsar_workflow_service.CCPA_SLA_DAYS
    assert dsar_workflow_service._sla_days_for("us-ca-something") == 45


def test_dsar_sla_days_recognises_labelled_jurisdictions():
    # Strings produced by privacy_jurisdiction.resolve_default_consent_for
    assert dsar_workflow_service._sla_days_for("US-PRIVACY:US-CA") == 45
    assert dsar_workflow_service._sla_days_for("CCPA:US-CA") == 45
    assert dsar_workflow_service._sla_days_for("GDPR:DE") == 30
    assert dsar_workflow_service._sla_days_for("GPC") == 30


def test_dsar_state_machine_rejects_terminal_reopen():
    # Simulate the FOR-UPDATE branch by patching get_db_connection.
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = {"status": "completed"}
    fake_cur.__enter__ = lambda self: self
    fake_cur.__exit__ = lambda *a: False
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    @contextmanager
    def _fake_conn_cm():
        yield fake_conn

    with patch("app.services.dsar_workflow_service.get_database_url", return_value="postgres://x"), \
         patch("app.services.dsar_workflow_service.get_db_connection", _fake_conn_cm):
        with pytest.raises(ValueError, match="not permitted"):
            dsar_workflow_service.transition(
                request_id="11111111-1111-1111-1111-111111111111",
                new_status="open",
                actor_id=ADMIN_ID,
            )


def test_dsar_state_machine_allows_open_to_in_progress():
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = {"status": "open"}
    fake_cur.rowcount = 1
    fake_cur.__enter__ = lambda self: self
    fake_cur.__exit__ = lambda *a: False
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    @contextmanager
    def _fake_conn_cm():
        yield fake_conn

    with patch("app.services.dsar_workflow_service.get_database_url", return_value="postgres://x"), \
         patch("app.services.dsar_workflow_service.get_db_connection", _fake_conn_cm), \
         patch("app.services.dsar_workflow_service.record_security_event"):
        ok = dsar_workflow_service.transition(
            request_id="11111111-1111-1111-1111-111111111111",
            new_status="in_progress",
            actor_id=ADMIN_ID,
        )
    assert ok is True


def test_self_service_persistence_failure_emits_audit_event():
    """If the workflow row write fails, an explicit failure audit event
    must be recorded so the SOC2 evidence gap is visible in SIEM."""
    from app.routes import dsar_routes as dr
    from unittest.mock import MagicMock

    fake_request = MagicMock()
    fake_request.headers = {}
    fake_request.client = None

    with patch("app.routes.dsar_routes._resolve_jurisdiction", return_value="US-PRIVACY:US-CA"), \
         patch(
             "app.services.dsar_workflow_service.open_request",
             side_effect=RuntimeError("simulated db outage"),
         ), \
         patch("app.routes.dsar_routes._emit_dsar_event") as emit_mock:
        dr._record_workflow_row(
            request=fake_request, request_type="access", user_id=USER_ID
        )

    actions = [c.kwargs.get("action") for c in emit_mock.call_args_list]
    assert "dsar_workflow_persist_failed" in actions
    failure_call = next(
        c for c in emit_mock.call_args_list
        if c.kwargs.get("action") == "dsar_workflow_persist_failed"
    )
    assert failure_call.kwargs.get("outcome") == "failure"
    assert failure_call.kwargs["metadata"]["jurisdiction"] == "US-PRIVACY:US-CA"
    assert failure_call.kwargs["metadata"]["request_type"] == "access"


def test_dsar_open_request_rejects_unknown_type():
    with pytest.raises(ValueError):
        dsar_workflow_service.open_request(request_type="not_a_real_type")


def test_dsar_transition_rejects_unknown_status():
    with pytest.raises(ValueError):
        dsar_workflow_service.transition(
            request_id="x", new_status="banana", actor_id=ADMIN_ID
        )


def test_breach_timer_deadline_for_gdpr_is_72h():
    opened = datetime(2026, 4, 19, tzinfo=timezone.utc)
    deadline = breach_timer_service._deadline_for("gdpr", opened)
    assert deadline == opened + timedelta(hours=72)


def test_breach_timer_deadline_for_hipaa_is_60d():
    opened = datetime(2026, 4, 19, tzinfo=timezone.utc)
    deadline = breach_timer_service._deadline_for("hipaa", opened)
    assert deadline == opened + timedelta(days=60)


def test_breach_timer_open_rejects_unknown_kind():
    with pytest.raises(ValueError):
        breach_timer_service.open_breach_timer(
            incident_id="i-1", kind="solar-flare", actor_id=ADMIN_ID
        )


# ---------------------------------------------------------------------------
# Admin route gating
# ---------------------------------------------------------------------------


def test_admin_dsar_list_rejects_non_admin(nonadmin_client):
    resp = nonadmin_client.get("/api/admin/dsar/requests")
    assert resp.status_code == 403


def test_admin_dsar_list_returns_rows_for_admin(admin_client):
    fake_rows = [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "type": "access",
            "status": "open",
            "due_at": "2026-05-19T00:00:00+00:00",
        }
    ]
    with patch(
        "app.routes.dsar_admin_routes.dsar_workflow_service.list_requests",
        return_value=fake_rows,
    ):
        resp = admin_client.get("/api/admin/dsar/requests?status=open")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["requests"][0]["status"] == "open"


def test_admin_dsar_open_request_validates_type(admin_client):
    resp = admin_client.post(
        "/api/admin/dsar/requests", json={"type": "totally-invalid-type"}
    )
    assert resp.status_code == 400


def test_admin_dsar_open_request_persists_via_service(admin_client):
    with patch(
        "app.routes.dsar_admin_routes.dsar_workflow_service.open_request",
        return_value="11111111-1111-1111-1111-111111111111",
    ) as m:
        resp = admin_client.post(
            "/api/admin/dsar/requests",
            json={"type": "access", "subject_user_id": USER_ID},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "11111111-1111-1111-1111-111111111111"
    assert body["status"] == "open"
    assert m.call_args.kwargs["request_type"] == "access"
    assert m.call_args.kwargs["created_by"] == ADMIN_ID


def test_admin_dsar_transition_404_when_unknown(admin_client):
    with patch(
        "app.routes.dsar_admin_routes.dsar_workflow_service.transition",
        return_value=False,
    ):
        resp = admin_client.post(
            "/api/admin/dsar/requests/missing-id/transition",
            json={"new_status": "in_progress"},
        )
    assert resp.status_code == 404


def test_admin_dsar_transition_400_on_invalid_status(admin_client):
    def _raise(**_kw):
        raise ValueError("invalid status: 'banana'")

    with patch(
        "app.routes.dsar_admin_routes.dsar_workflow_service.transition",
        side_effect=_raise,
    ):
        resp = admin_client.post(
            "/api/admin/dsar/requests/some-id/transition",
            json={"new_status": "banana"},
        )
    assert resp.status_code == 400


def test_admin_breach_open_rejects_non_admin(nonadmin_client):
    resp = nonadmin_client.post(
        "/api/admin/incidents/breach-timers",
        json={"incident_id": "INC-1", "kind": "gdpr"},
    )
    assert resp.status_code == 403


def test_admin_breach_open_for_admin(admin_client):
    with patch(
        "app.routes.dsar_admin_routes.breach_timer_service.open_breach_timer",
        return_value="22222222-2222-2222-2222-222222222222",
    ) as m:
        resp = admin_client.post(
            "/api/admin/incidents/breach-timers",
            json={
                "incident_id": "INC-1",
                "kind": "gdpr",
                "affected_count": 12,
                "affected_jurisdiction": "EU-DE",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"].startswith("22222222")
    assert body["status"] == "open"
    assert m.call_args.kwargs["kind"] == "gdpr"
    assert m.call_args.kwargs["actor_id"] == ADMIN_ID


def test_admin_breach_list_returns_active_timers(admin_client):
    with patch(
        "app.routes.dsar_admin_routes.breach_timer_service.find_due",
        return_value=[{"id": "t1", "kind": "gdpr", "status": "open"}],
    ):
        resp = admin_client.get("/api/admin/incidents/breach-timers?within_hours=72")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["timers"][0]["kind"] == "gdpr"


def test_admin_breach_notify_404_when_unknown(admin_client):
    with patch(
        "app.routes.dsar_admin_routes.breach_timer_service.record_notification",
        return_value=False,
    ):
        resp = admin_client.post(
            "/api/admin/incidents/breach-timers/missing/notify", json={}
        )
    assert resp.status_code == 404


def test_admin_breach_close_404_when_unknown(admin_client):
    with patch(
        "app.routes.dsar_admin_routes.breach_timer_service.close_timer",
        return_value=False,
    ):
        resp = admin_client.post(
            "/api/admin/incidents/breach-timers/missing/close"
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Deadline checker script — emits correct audit event types
# ---------------------------------------------------------------------------


def test_deadline_checker_emits_breached_then_warning_for_dsar():
    from scripts import check_dsar_deadlines

    breached_row = {"id": "b1", "type": "access", "due_at": "2026-04-18T00:00:00+00:00"}
    warning_row = {"id": "w1", "type": "access", "due_at": "2026-04-20T00:00:00+00:00"}

    def _find_overdue(window_hours: int = 0):
        if window_hours == 0:
            return [breached_row]
        # warn window includes both
        return [breached_row, warning_row]

    emitted = []

    def _record_event(event_type, **kwargs):
        emitted.append((event_type, kwargs.get("target_id")))

    with patch.object(check_dsar_deadlines, "find_overdue", side_effect=_find_overdue), patch.object(
        check_dsar_deadlines, "record_security_event", side_effect=_record_event
    ):
        result = check_dsar_deadlines.check_dsar(warn_hours=48)

    assert result == {"breached": 1, "warning": 1}
    types = {e[0] for e in emitted}
    assert "dsar_deadline_breached" in types
    assert "dsar_deadline_warning" in types


def test_deadline_checker_classifies_breach_timer_rows_correctly():
    from scripts import check_dsar_deadlines

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(hours=10)).isoformat()
    rows = [
        {"id": "t-past", "kind": "gdpr", "deadline_at": past, "status": "open"},
        {"id": "t-future", "kind": "hipaa", "deadline_at": future, "status": "open"},
    ]

    emitted = []

    def _record_event(event_type, **kwargs):
        emitted.append((event_type, kwargs.get("target_id")))

    with patch.object(check_dsar_deadlines, "find_due_breach", return_value=rows), patch.object(
        check_dsar_deadlines, "record_security_event", side_effect=_record_event
    ):
        result = check_dsar_deadlines.check_breach_timers(warn_hours=24)

    assert result == {"breached": 1, "warning": 1}
    by_id = dict((tid, et) for et, tid in emitted)
    assert by_id["t-past"] == "breach_timer_deadline_breached"
    assert by_id["t-future"] == "breach_timer_deadline_warning"
