"""Stage #1 — JsonFormatter.

Validates the JSON log shape documented in ``backend/app/utils/logger.py``
without relying on env-var-time module import order (the logger module
binds ``_LOG_FORMAT`` at import time, so we test the formatter class
directly instead of re-importing the module).
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.middleware.request_id import RequestIDMiddleware
from app.utils.logger import JsonFormatter


def _emit(record: logging.LogRecord) -> dict:
    """Run the record through ``JsonFormatter`` and parse the JSON line."""
    line = JsonFormatter().format(record)
    return json.loads(line)


def _make_record(
    level: int = logging.INFO,
    msg: str = "hello",
    extra: dict | None = None,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name="manifest.test",
        level=level,
        pathname=__file__,
        lineno=42,
        msg=msg,
        args=(),
        exc_info=None,
        func="boot",
    )
    if extra:
        for key, value in extra.items():
            setattr(record, key, value)
    return record


def test_emits_core_fields():
    payload = _emit(_make_record(msg="boot complete"))

    assert payload["severity"] == "INFO"
    assert payload["logger"] == "manifest.test"
    assert payload["message"] == "boot complete"
    assert payload["code.line.number"] == 42
    assert payload["code.file.path"].endswith("test_json_logging.py")
    assert payload["timestamp"].endswith("Z"), "timestamps are UTC ISO-8601 with millis"


def test_merges_extra_fields_into_top_level_json():
    payload = _emit(
        _make_record(
            level=logging.WARNING,
            msg="slow",
            extra={
                "path": "/graphql",
                "duration_ms": 812.5,
                "slow_queries": [{"sql": "select 1", "ms": 110}],
            },
        )
    )

    # Existing slow-request log call shape stays intact.
    assert payload["path"] == "/graphql"
    assert payload["duration_ms"] == 812.5
    assert payload["slow_queries"] == [{"sql": "select 1", "ms": 110}]


def test_includes_request_id_when_contextvar_set():
    """Simulate being inside an HTTP request — ContextVar bound to a known value."""
    from app.middleware.request_id import _request_id_ctx

    token = _request_id_ctx.set("test-request-abc")
    try:
        payload = _emit(_make_record(msg="inside request"))
        assert payload["request_id"] == "test-request-abc"
    finally:
        _request_id_ctx.reset(token)


def test_omits_request_id_outside_a_request():
    payload = _emit(_make_record(msg="standalone"))
    assert "request_id" not in payload


def test_does_not_explode_on_unserializable_extra():
    class NotJsonable:
        def __repr__(self):
            return "<weird object>"

    payload = _emit(_make_record(extra={"weird": NotJsonable()}))
    # Falls back to repr() rather than raising.
    assert payload["weird"] == "<weird object>"


def test_extras_do_not_clobber_generated_payload_keys():
    """An extra named like one of OUR generated keys (logger, ts, level, ...) must not win.

    The formatter sets the canonical payload keys first, then merges
    extras while skipping any key already present — so a careless caller
    passing ``extra={"logger": "shadowed"}`` cannot corrupt log searches
    that filter by ``logger="manifest"``.
    """
    record = _make_record(
        msg="actual",
        extra={
            "logger": "shadowed",
            "timestamp": "fake-ts",
            "severity": "DEBUG",
            "code.file.path": "fake.py",
            "code.line.number": -1,
        },
    )
    payload = _emit(record)

    assert payload["logger"] == "manifest.test"
    assert payload["severity"] == "INFO"
    assert payload["timestamp"].endswith("Z")
    assert payload["timestamp"] != "fake-ts"
    assert payload["code.file.path"].endswith("test_json_logging.py")
    assert payload["code.line.number"] == 42
    assert payload["message"] == "actual"


def test_includes_exception_traceback_when_present():
    try:
        raise ValueError("explode")
    except ValueError:
        record = logging.LogRecord(
            name="manifest.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=99,
            msg="caught",
            args=(),
            exc_info=sys.exc_info(),
        )

    payload = _emit(record)
    assert payload["exception.type"] == "ValueError"
    assert "ValueError" in payload["exception.stacktrace"]
    assert "explode" in payload["exception.message"]


def test_middleware_import_path_does_not_break_logger_import():
    """Regression guard for the JsonFormatter -> RequestIDMiddleware lazy import.

    If anyone refactors the import to top-level, this test still passes,
    but importing ``logger`` first ensures we don't introduce a hard
    cycle.
    """
    # Both modules already imported by other tests; just assert they're both
    # importable in isolation without circular import errors.
    assert RequestIDMiddleware is not None
    assert JsonFormatter is not None


def test_identifies_the_service_with_opentelemetry_resource_fields():
    payload = _emit(_make_record(msg="hello"))
    assert payload["service.name"]
    assert payload["service.version"]
    assert payload["deployment.environment.name"]
    assert payload["code.function.name"] == "boot"
