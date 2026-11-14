"""Tests for SecurityHeadersMiddleware (Task #13 / SEC-002)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security.security_headers import (
    SecurityHeadersMiddleware,
    baseline_security_header_keys,
)


def _make_app(*, enforce: bool = False) -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, enforce_csp=enforce)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return TestClient(app)


def test_baseline_headers_present_on_every_response():
    client = _make_app()
    resp = client.get("/ping")
    assert resp.status_code == 200
    for header in baseline_security_header_keys():
        assert header in resp.headers, f"missing {header}"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_csp_defaults_to_report_only():
    client = _make_app(enforce=False)
    resp = client.get("/ping")
    assert "Content-Security-Policy-Report-Only" in resp.headers
    assert "Content-Security-Policy" not in resp.headers
    csp = resp.headers["Content-Security-Policy-Report-Only"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp


def test_csp_enforced_mode_uses_canonical_header():
    client = _make_app(enforce=True)
    resp = client.get("/ping")
    assert "Content-Security-Policy" in resp.headers
    assert "Content-Security-Policy-Report-Only" not in resp.headers


def test_csp_defaults_to_enforced_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    resp = TestClient(app).get("/ping")
    assert "Content-Security-Policy" in resp.headers
    assert "Content-Security-Policy-Report-Only" not in resp.headers


def test_each_response_has_unique_csp_nonce():
    client = _make_app()
    a = client.get("/ping").headers["X-CSP-Nonce"]
    b = client.get("/ping").headers["X-CSP-Nonce"]
    assert a and b and a != b


def test_csp_includes_nonce_in_script_src():
    client = _make_app()
    resp = client.get("/ping")
    nonce = resp.headers["X-CSP-Nonce"]
    csp = resp.headers["Content-Security-Policy-Report-Only"]
    assert f"'nonce-{nonce}'" in csp


def test_hsts_absent_on_plain_http_in_dev(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    client = _make_app()
    resp = client.get("/ping")
    assert "Strict-Transport-Security" not in resp.headers


def test_hsts_present_when_env_is_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    client = _make_app()
    resp = client.get("/ping")
    assert "Strict-Transport-Security" in resp.headers
    assert "max-age=" in resp.headers["Strict-Transport-Security"]
