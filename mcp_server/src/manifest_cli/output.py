"""Readable terminal output; ``--json`` prints the raw value instead."""

from __future__ import annotations

import json
import shutil
from typing import Any

MAX_CELL = 48
MAX_VALUE = 400


def _short(value: Any, limit: int) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, dict | list) else str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _is_flat_rows(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(row, dict) for row in value)


def table(rows: list[dict[str, Any]]) -> str:
    columns: list[str] = []
    for row in rows:
        for key, val in row.items():
            if key not in columns and not isinstance(val, dict | list):
                columns.append(key)
    if not columns:
        return "\n\n".join(render(row) for row in rows)
    width = shutil.get_terminal_size((120, 20)).columns
    # Keep as many leading columns as fit the terminal.
    cells = [[_short(row.get(c), MAX_CELL) for c in columns] for row in rows]
    widths = [max(len(c), *(len(r[i]) for r in cells)) for i, c in enumerate(columns)]
    keep, used = 0, 0
    for w in widths:
        if keep and used + w + 2 > width:
            break
        used += w + 2
        keep += 1
    lines = ["  ".join(c.ljust(widths[i]) for i, c in enumerate(columns[:keep])).rstrip()]
    lines.append("  ".join("-" * widths[i] for i in range(keep)))
    for r in cells:
        lines.append("  ".join(r[i].ljust(widths[i]) for i in range(keep)).rstrip())
    if keep < len(columns):
        lines.append(f"({len(columns) - keep} more columns: use --json or --select)")
    return "\n".join(lines)


def render(value: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if _is_flat_rows(value) and indent == 0:
        return table(value)
    if isinstance(value, dict):
        if not value:
            return pad + "(empty)"
        key_width = max(len(str(k)) for k in value)
        lines = []
        for key, val in value.items():
            if isinstance(val, dict) and val:
                lines.append(f"{pad}{key}:")
                lines.append(render(val, indent + 1))
            elif isinstance(val, list) and val and isinstance(val[0], dict):
                lines.append(f"{pad}{key}: ({len(val)})")
                for item in val:
                    lines.append(render(item, indent + 1))
                    lines.append("")
            else:
                lines.append(f"{pad}{str(key).ljust(key_width)}  {_short(val, MAX_VALUE)}")
        return "\n".join(line for line in lines).rstrip()
    if isinstance(value, list):
        if not value:
            return pad + "(none)"
        return "\n".join(pad + "- " + _short(v, MAX_VALUE) for v in value)
    return pad + _short(value, 10_000)


def emit(value: Any, *, as_json: bool, out) -> None:
    if as_json:
        out.write(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")
    else:
        out.write(render(value) + "\n")
