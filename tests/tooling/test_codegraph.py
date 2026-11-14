"""Contract tests for scripts/codegraph (build + query against the real repo)."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUERY = ROOT / "scripts" / "codegraph" / "query.py"


def run(*args: str):
    out = subprocess.run(
        [sys.executable, str(QUERY), *args, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)


def test_graph_builds_with_containment_and_imports():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/codegraph/build.py"), "--quiet"], cwd=ROOT, check=True
    )
    graph = json.loads((ROOT / ".codegraph" / "graph.json").read_text())
    nodes = graph["nodes"]
    main = nodes["backend/app/main.py"]
    assert main["parent"] == "backend/app"
    assert nodes["backend/app"]["parent"] == "backend"
    assert main["imports"], "main.py should import application modules"
    assert graph["routes"] and graph["graphql"]


def test_python_and_typescript_importers_resolve():
    assert "backend/app/routes/sso_routes.py" in run("parents", "backend/app/security/cookies.py")
    ts_parents = run("parents", "frontend/src/features/ideas/utils/syncIdeaTitleCache.ts")
    assert "frontend/src/features/ideas/components/Idea.tsx" in ts_parents  # '../' import


def test_impact_includes_transitive_dependents():
    rows = run("impact", "backend/app/db/rows.py")
    files = {r["file"] for r in rows}
    assert "backend/app/services/dsar_workflow_service.py" in files
    assert any(r["hops"] > 1 for r in rows)


def test_outline_and_find_point_at_definitions():
    outline = run("outline", "backend/app/db/rows.py")
    assert any(r["id"] == "rows_to_dicts" for r in outline)
    found = run("find", "rows_to_dicts")
    assert found[0]["at"].startswith("backend/app/db/rows.py:")


def test_guide_returns_parent_then_child():
    assert run("guide", "backend/app/main.py") == ["AGENTS.md", "backend/AGENTS.md"]


def test_routes_map_to_handlers():
    routes = run("routes", "/api/sso")
    assert routes and all("::" in r["handler"] for r in routes)


def test_graphql_fields_use_camel_case_names():
    assert run("graphql", "pitchReelsFeed")


def test_tools_run_on_the_macos_system_python():
    """Docs say `python3 scripts/...`; on macOS that is Python 3.9, not the venv."""
    import pytest

    system_python = Path("/usr/bin/python3")
    if not system_python.exists():
        pytest.skip("no system python3")
    for script, args in (
        ("scripts/codegraph/build.py", ["--quiet"]),
        ("scripts/codegraph/query.py", ["stats", "--json"]),
    ):
        subprocess.run(
            [str(system_python), script, *args], cwd=ROOT, check=True, capture_output=True
        )
