"""Prometheus instrumentation — Stage #1 of the backend migration.

Exposes ``/metrics`` in the Prometheus text exposition format so any
external scraper (Grafana Cloud, Datadog, Prometheus, OpenObserve) can
pull RED-style metrics for every HTTP route — not just GraphQL.

Why a lazy import
-----------------
``prometheus-fastapi-instrumentator`` is the only **new** runtime
dependency in this stage. We import it lazily so:

* Local dev environments without the pinned dep can still boot.
* Offline / sandboxed test environments stay green.
* If a future runtime swap (e.g. moving to OpenTelemetry-only) drops
  this dep, /metrics returns 404 quietly instead of crashing boot.

Defense in depth
----------------
``/metrics`` is intentionally unauthenticated so a Prometheus scraper
need no credential. Network-level protection is the primary defense:

* On Render, host the API on a *private* service and scrape from a
  sibling Grafana Agent container.
* On Vercel rewrites, deny ``/metrics`` at the edge for public traffic.

Set ``METRICS_ENABLED=false`` to disable entirely.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from app.utils.logger import logger

if TYPE_CHECKING:
    from fastapi import FastAPI


_METRICS_NAMESPACE = "manifest"
_METRICS_SUBSYSTEM = "http"
_EXCLUDED_PATHS = ["/ping", "/metrics", "/health", "/healthz"]


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def metrics_enabled() -> bool:
    """Default-on. Set ``METRICS_ENABLED=false`` to skip wiring."""
    raw = os.getenv("METRICS_ENABLED")
    if raw is None:
        return True
    return _truthy(raw)


def setup_metrics(app: FastAPI) -> bool:
    """Wire prometheus-fastapi-instrumentator into ``app``.

    Returns ``True`` if instrumentation was attached, ``False`` if it was
    skipped (dep missing, or ``METRICS_ENABLED=false``). Idempotent on a
    single app (uses ``app.state._metrics_attached`` as a guard) — safe to
    call once at startup or repeatedly under hot-reload.

    Per-app ``CollectorRegistry``
    -----------------------------
    Each app gets its own ``CollectorRegistry`` (rather than the global
    ``prometheus_client.REGISTRY``) so multiple ``FastAPI`` instances in
    the same Python process — tests, hot-reload, vendored sub-apps — do
    not collide on ``manifest_http_inprogress`` and the other default
    metric names. The custom registry is propagated to the underlying
    ASGI middleware via the Instrumentator's ``registry=`` parameter.
    The registry is stashed on ``app.state._metrics_registry`` for any
    test that wants to introspect it.
    """
    if not metrics_enabled():
        logger.info("[metrics] disabled via METRICS_ENABLED=false")
        return False

    if getattr(app.state, "_metrics_attached", False):
        return True

    try:
        from prometheus_client import CollectorRegistry
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError:
        logger.warning(
            "[metrics] prometheus-fastapi-instrumentator not installed; "
            "/metrics will not be available. "
            "Run `pip install prometheus-fastapi-instrumentator` to enable."
        )
        return False

    registry = CollectorRegistry()

    # NOTE: ``should_instrument_requests_inprogress=False`` is intentional.
    # prometheus-fastapi-instrumentator v7.1.0 has a bug where the inprogress
    # Gauge is created without ``registry=self.registry`` (see
    # site-packages/prometheus_fastapi_instrumentator/middleware.py:117) — so
    # the gauge always lands in the global ``prometheus_client.REGISTRY`` and
    # collides on the second app in the same Python process. The duration
    # histogram already captures the in-flight signal indirectly via rate /
    # latency, and we can re-add a properly-scoped custom Gauge later if
    # an SRE actually needs the live in-progress count.
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=False,
        excluded_handlers=_EXCLUDED_PATHS,
        registry=registry,
    )

    instrumentator.instrument(
        app,
        metric_namespace=_METRICS_NAMESPACE,
        metric_subsystem=_METRICS_SUBSYSTEM,
    )
    instrumentator.expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        should_gzip=True,
    )
    app.state._metrics_attached = True
    app.state._metrics_registry = registry
    logger.info("[metrics] /metrics endpoint registered (namespace=manifest)")
    return True
