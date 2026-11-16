"""Drift guard: the committed Manifest CLI catalog must match the GraphQL schema.

Fails after any schema change until the catalog is regenerated with
``.venv/bin/python scripts/generate_cli_catalog.py`` (also run by ``scripts/check.py``, area ``cli``).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "generate_cli_catalog.py"
CATALOG = ROOT / "mcp_server" / "src" / "manifest_cli" / "catalog.json"

pytest.importorskip("strawberry", reason="needs the backend dependencies (.venv)")


def test_cli_catalog_matches_the_graphql_schema():
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-2000:]


def test_catalog_has_every_operation_once():
    catalog = json.loads(CATALOG.read_text())
    names = [(op["kind"], op["name"]) for op in catalog["operations"]]
    assert len(names) == len(set(names))
    assert {kind for kind, _ in names} == {"query", "mutation"}
    assert all(op["command"] and op["returns"] for op in catalog["operations"])
