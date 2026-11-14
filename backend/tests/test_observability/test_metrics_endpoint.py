"""Stage #1 — /metrics endpoint.

Validates the contract documented in ``backend/app/middleware/metrics.py``:

* ``METRICS_ENABLED=false`` skips wiring (and returns False).
* When enabled and the dep is installed, ``/metrics`` returns a 200 with
  Prometheus text exposition format and at least one ``manifest_*`` metric.
* The endpoint and ``/ping`` are excluded from the instrumentator's
  request histograms (otherwise the scraper measures itself).
"""

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.middleware.metrics import metrics_enabled, setup_metrics


def _has_instrumentator() -> bool:
    try:
        import prometheus_fastapi_instrumentator  # noqa: F401
    except ImportError:
        return False
    return True


def test_metrics_enabled_default_is_true(monkeypatch):
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    assert metrics_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off"])
def test_metrics_enabled_respects_falsy_env(monkeypatch, value):
    monkeypatch.setenv("METRICS_ENABLED", value)
    assert metrics_enabled() is False


def test_setup_metrics_returns_false_when_disabled(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "false")
    app = FastAPI()
    assert setup_metrics(app) is False
    # Endpoint must not be registered.
    client = TestClient(app)
    assert client.get("/metrics").status_code == 404


@pytest.mark.skipif(
    not _has_instrumentator(),
    reason="prometheus-fastapi-instrumentator not installed in this env",
)
def test_metrics_endpoint_returns_prometheus_exposition(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "true")
    app = FastAPI()

    @app.get("/work")
    async def work():
        return {"ok": True}

    attached = setup_metrics(app)
    assert attached is True

    client = TestClient(app)
    # Generate one request so the histogram has at least one sample.
    assert client.get("/work").status_code == 200

    response = client.get("/metrics")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    # Prometheus text exposition format
    assert "text/plain" in content_type or "openmetrics-text" in content_type
    body = response.text
    # The instrumentator namespace from our setup is "manifest_http_*"
    assert "manifest_http" in body, (
        "expected manifest_http_* metric prefix; got first 500 chars: " + body[:500]
    )


@pytest.mark.skipif(
    not _has_instrumentator(),
    reason="prometheus-fastapi-instrumentator not installed in this env",
)
def test_metrics_endpoint_does_not_instrument_itself(monkeypatch):
    """A scrape of /metrics must not show up as a /metrics request in the histogram.

    Otherwise Grafana sees an infinite self-referential growth.
    """
    monkeypatch.setenv("METRICS_ENABLED", "true")
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    setup_metrics(app)
    client = TestClient(app)

    # Generate a /ping request to confirm the exclusion list is honored.
    client.get("/ping")
    # Scrape twice; the body should NOT mention /metrics or /ping as labels.
    client.get("/metrics")
    body = client.get("/metrics").text
    assert 'handler="/metrics"' not in body
    assert 'handler="/ping"' not in body

