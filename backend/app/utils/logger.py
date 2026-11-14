"""Centralized logger for the Manifest backend.

Stage #1 of the backend migration upgrades this from a single plain-text
handler to a logger that can emit either:

* ``LOG_FORMAT=text`` (default in dev) — the existing ``[%(asctime)s] ...``
  layout so local ``run.py`` output stays human-readable.
* ``LOG_FORMAT=json`` (default in prod when set via Render env var) — one
  JSON document per line, suitable for any aggregator (Grafana Loki,
  Datadog, CloudWatch, OpenObserve, etc.).

The JSON formatter automatically threads in the ``X-Request-Id`` set by
:mod:`app.middleware.request_id`, so every log line can be filtered down
to a single request without the caller having to thread the ID through.

No new dependency — uses ``json`` + ``traceback`` from stdlib.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from typing import Any

_LOG_LEVEL = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
_LOG_FORMAT = (os.getenv("LOG_FORMAT") or "text").strip().lower()

# Stdlib LogRecord attributes we must not re-emit as user-defined extras.
_RESERVED_LOGRECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def _format_timestamp(created: float) -> str:
    millis = int((created - int(created)) * 1000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(created)) + f".{millis:03d}Z"


def _safe_json_value(value: Any) -> Any:
    """Coerce a value into something ``json.dumps`` can handle."""
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)
    return value


class JsonFormatter(logging.Formatter):
    """Minimal stdlib-only JSON log formatter.

    Each log record becomes a single JSON line::

        {"ts":"...","level":"INFO","logger":"manifest","msg":"...",
         "file":"main.py","line":42,"request_id":"...","custom":"..."}

    ``extra=`` keys from the caller are merged into the top-level JSON,
    so existing slow-query log calls (which already pass structured
    fields like ``query_count`` / ``slow_queries``) keep working without
    any caller changes.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Import here to avoid a circular import: request_id has no deps,
        # but importing this module at request_id load time would create
        # a hot loop on first cold start.
        from app.middleware.request_id import get_request_id

        payload: dict[str, Any] = {
            "ts": _format_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "file": record.filename,
            "line": record.lineno,
        }

        rid = get_request_id()
        if rid:
            payload["request_id"] = rid

        for key, value in record.__dict__.items():
            if key in _RESERVED_LOGRECORD_ATTRS or key in payload:
                continue
            if key.startswith("_"):
                continue
            payload[key] = _safe_json_value(value)

        if record.exc_info:
            payload["exc"] = "".join(traceback.format_exception(*record.exc_info))
        if record.stack_info:
            payload["stack"] = record.stack_info

        return json.dumps(payload, ensure_ascii=False, default=str)


def _build_handler() -> logging.Handler:
    handler = logging.StreamHandler(stream=sys.stdout)
    if _LOG_FORMAT in {"json", "structured"}:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] [%(levelname)s] %(name)s: " "%(filename)s:%(lineno)d - %(message)s"
            )
        )
    return handler


logger = logging.getLogger("manifest")
try:
    logger.setLevel(_LOG_LEVEL)
except (TypeError, ValueError):
    logger.setLevel(logging.INFO)

if not logger.hasHandlers():
    logger.addHandler(_build_handler())

# Allow log records to propagate to parent handlers so test harnesses and
# external collectors can capture them alongside the console stream.
logger.propagate = True


def log_exception(msg: str, *args, **kwargs):
    """Log an exception with traceback using the manifest logger."""
    logger.error(msg, *args, exc_info=True, **kwargs)
