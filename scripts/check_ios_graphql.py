#!/usr/bin/env python3
"""Validate every GraphQL operation in the iOS app against the backend schema.

The app keeps its operations as Swift string literals in
``ios/Manifest Startup/Core/Networking/API.swift``; fragments are ``static let``
strings spliced in with ``\\(name)``. This expands them and runs graphql-core
validation, so a renamed field or argument fails locally instead of in the app.

    python3 scripts/check_ios_graphql.py        # exit 1 on any invalid operation
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_SWIFT = ROOT / "ios" / "Manifest Startup" / "Core" / "Networking" / "API.swift"

_TRIPLE = re.compile(r'"""\n(.*?)\n\s*"""', re.S)
_SINGLE = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
_STATIC = re.compile(r"static let (\w+) = ")
_INTERP = re.compile(r"\\\((\w+)\)")


def _literal_after(source: str, start: int) -> str | None:
    """The string literal that begins at ``start`` (single or triple quoted)."""
    if source.startswith('"""', start):
        match = _TRIPLE.match(source, start)
        return _clean_triple(match.group(1)) if match else None
    match = _SINGLE.match(source, start)
    return match.group(1) if match else None


def _clean_triple(body: str) -> str:
    # A trailing backslash joins lines in Swift multi-line strings.
    return re.sub(r"\\\n\s*", "", body)


def extract(source: str) -> tuple[dict[str, str], list[str]]:
    fragments: dict[str, str] = {}
    for match in _STATIC.finditer(source):
        literal = _literal_after(source, match.end())
        if literal is not None:
            fragments[match.group(1)] = literal

    operations: list[str] = []
    for match in re.finditer(r'"""\n|"', source):
        literal = _literal_after(source, match.start())
        if literal and re.match(r"\s*(query|mutation)\s+\w+", literal):
            operations.append(literal)

    def expand(text: str, depth: int = 0) -> str:
        if depth > 5:
            return text
        return _INTERP.sub(lambda m: expand(fragments.get(m.group(1), m.group(0)), depth + 1), text)

    return fragments, sorted({expand(op) for op in operations})


def main() -> int:
    sys.path.insert(0, str(ROOT / "backend"))
    import logging

    logging.disable(logging.CRITICAL)
    from app.graphql.schema import schema  # noqa: E402
    from graphql import build_schema, parse, validate  # noqa: E402

    graphql_schema = build_schema(schema.as_str())
    _, operations = extract(API_SWIFT.read_text())
    failures = []
    for op in operations:
        try:
            errors = validate(graphql_schema, parse(op))
        except Exception as exc:  # syntax errors
            errors = [exc]
        if errors:
            name = re.match(r"\s*\w+\s+(\w+)", op)
            failures.append(f"{name.group(1) if name else op[:40]}: {errors[0]}")
    if failures:
        print("\n".join(failures))
        print(f"{len(failures)} of {len(operations)} iOS operations are invalid")
        return 1
    print(f"{len(operations)} iOS GraphQL operations valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
