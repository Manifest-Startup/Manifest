"""PII redaction at the audit-writer boundary.

The chain row + SIEM stream must NEVER contain raw email addresses
in any top-level canonical identity field. We assert this by mocking
the DB and the sink, calling record_security_event with email-shaped
target_id / actor_id / tenant_id, and inspecting what actually gets
persisted/emitted.
"""

from __future__ import annotations

from unittest.mock import patch

from app.services import security_audit_service


class _Cur:
    def __init__(self):
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        if params and "INSERT" in sql.upper():
            self.params = params

    def fetchone(self):
        return None


class _Conn:
    def __init__(self, cur):
        self._cur = cur

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self._cur

    def commit(self):
        pass


def test_email_target_id_is_pseudonymized_before_persistence():
    cur = _Cur()
    sink_calls = []

    def _fake_emit(**kw):
        sink_calls.append(kw)

    with patch.object(
        security_audit_service, "get_db_connection", side_effect=lambda: _Conn(cur)
    ), patch.object(security_audit_service.audit_sink, "emit", side_effect=_fake_emit):
        security_audit_service.record_security_event(
            "login_failed",
            target_id="Alice@Example.COM",
            actor_id="bob@example.com",
            tenant_id="tenant@example.org",
            target_type="user",
            action="login",
            outcome="failure",
        )

    # Persisted INSERT params include actor_id, target_id, tenant_id
    # in known column positions — pull them out and assert no '@'.
    assert cur.params is not None
    persisted = list(cur.params)
    for v in persisted:
        if isinstance(v, str):
            assert "@example" not in v.lower(), f"raw email leaked into DB: {v!r}"
    # SIEM stream must also be redacted.
    assert sink_calls, "sink must be called"
    s = sink_calls[0]
    for key in ("actor_id", "target_id", "tenant_id"):
        v = s.get(key)
        if v is not None:
            assert v.startswith("email:"), f"{key} not pseudonymized: {v!r}"
            assert "@" not in v


def test_non_email_identifiers_are_passed_through():
    cur = _Cur()
    with patch.object(
        security_audit_service, "get_db_connection", side_effect=lambda: _Conn(cur)
    ), patch.object(security_audit_service.audit_sink, "emit", return_value=None):
        security_audit_service.record_security_event(
            "login_success",
            target_id="user-uuid-123",
            actor_id="user-uuid-123",
            tenant_id="acme-corp",
            target_type="user",
            action="login",
            outcome="success",
        )
    assert cur.params is not None
    # UUID-like + slug-like values must NOT be hashed.
    flat = " ".join(str(v) for v in cur.params if v is not None)
    assert "user-uuid-123" in flat
    assert "acme-corp" in flat
    assert "email:" not in flat


def test_canonical_schema_gap_warning_for_sensitive_event():
    """Sensitive events emitted without action/target_type/outcome
    must produce a structured warning so the gap is visible in CI."""
    cur = _Cur()
    warnings = []
    real_warning = security_audit_service.logger.warning

    def _capture(msg, *args, **kw):
        try:
            warnings.append(msg % args if args else msg)
        except Exception:
            warnings.append(str(msg))
        return real_warning(msg, *args, **kw)

    with patch.object(
        security_audit_service, "get_db_connection", side_effect=lambda: _Conn(cur)
    ), patch.object(security_audit_service.audit_sink, "emit", return_value=None), \
         patch.object(security_audit_service.logger, "warning", side_effect=_capture):
        security_audit_service.record_security_event(
            "login_failed",
            user_id="u1",
            # intentionally missing action/target_type/outcome
        )
    assert any("canonical-schema gap" in m for m in warnings), warnings
