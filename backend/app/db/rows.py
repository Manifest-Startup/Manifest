"""Helpers for turning DB-API rows into JSON-safe dicts."""

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any


def _json_value(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def rows_to_dicts(rows: Iterable[Any], keys: Sequence[str]) -> list[dict[str, Any]]:
    """Convert dict rows or tuple rows (ordered as ``keys``) to dicts with ISO-8601 datetimes."""
    out: list[dict[str, Any]] = []
    for row in rows:
        pairs = row.items() if isinstance(row, dict) else zip(keys, row, strict=False)
        out.append({k: _json_value(v) for k, v in pairs})
    return out
