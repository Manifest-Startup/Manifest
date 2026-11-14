#!/usr/bin/env python3
"""Query the Manifest code knowledge graph (.codegraph/graph.json).

The graph rebuilds itself when sources changed, so results are always current.

Commands:
    find <term>          symbols/files whose name matches (case-insensitive substring)
    tree <dir|file> [-d] containment children (parent -> child), depth -d (default 2)
    parents <file>       files that import <file>  (who depends on me)
    children <file>      files <file> imports      (what I depend on)
    impact <file>        transitive importers: blast radius of changing <file>
    outline <file>       classes / functions / methods in a file with line numbers
    routes [term]        FastAPI routes -> handler
    graphql [term]       Strawberry GraphQL fields -> resolver
    orphans              non-entry source files nothing imports (dead-module candidates)
    unused [path]        top-level symbols whose name never appears elsewhere (dead-code candidates)
    cycles               import cycles between files
    stats                size and coupling hot spots
    guide <path>         AGENTS.md chain (root parent -> nearest child) that governs <path>

Add --json to any command for machine-readable output.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / ".codegraph" / "graph.json"

# Files that are legitimately loaded by a runtime, a tool or a config file instead of an import.
ENTRY_PATTERNS = [
    "main.py",
    "*/main.py",
    "*/__init__.py",
    "*/__main__.py",
    "backend/app/workers/*",
    "*/conftest.py",
    "*/wsgi.py",
    "*/asgi.py",
    "backend/scripts/*",
    "scripts/*",
    "*/migrations/*",
    "*/alembic/*",
    "loadtest/*",
    "production-tests/*",
    "frontend/src/main.tsx",
    "frontend/src/index.tsx",
    "frontend/src/setupTests.*",
    "frontend/src/sw.*",
    "frontend/public/*",
    "frontend/scripts/*",
    "frontend/cypress/*",
    "*.config.*",
    "*rc.js",
    "*rc.cjs",
    "deploy/*",
    "extensions/*/src/extension.ts",
    "mcp_server/src/*/server.py",
    "src/manifest_dev/cli.py",
    "*.stories.*",
    "frontend/.storybook/*",
    "*/__mocks__/*",
]
# Text files that can reference a source file by path (Dockerfiles, workflows, package scripts...).
CONFIG_GLOBS = [
    "*.json",
    "*.jsonc",
    "*.toml",
    "*.yml",
    "*.yaml",
    "*.sh",
    "*.html",
    "*.ini",
    "*.cfg",
    "dockerfile",
    "Dockerfile",
    "Procfile",
    "*.config.js",
    "*.config.cjs",
    "*.config.mjs",
    "*.config.ts",
]


def load() -> dict:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/codegraph/build.py"), "--if-stale", "--quiet"],
        check=True,
    )
    return json.loads(GRAPH.read_text())


def emit(rows, as_json: bool, fmt) -> None:
    if as_json:
        print(json.dumps(rows, indent=1))
        return
    if not rows:
        print("(no results)")
    for r in rows:
        print(fmt(r))


def norm(g: dict, path: str) -> str:
    p = path.strip("/").removeprefix("./")
    if p in g["nodes"]:
        return p
    hits = [k for k, n in g["nodes"].items() if n["kind"] == "file" and k.endswith("/" + p)]
    if len(hits) == 1:
        return hits[0]
    sys.exit(f"'{path}' not found" + (f"; ambiguous: {hits[:8]}" if hits else ""))


def loc(n: dict) -> str:
    return f"{n.get('file', n['id'])}:{n.get('line', 1)}"


def cmd_find(g, a):
    t = a.arg.lower()
    rows = [n for n in g["nodes"].values() if t in n["name"].lower() and n["kind"] != "dir"]
    rows.sort(key=lambda n: (n["name"].lower() != t, n["kind"] == "file", n["id"]))
    emit(
        [
            {"kind": n["kind"], "name": n["name"], "at": loc(n), "doc": n.get("doc", "")}
            for n in rows[: a.limit]
        ],
        a.json,
        lambda r: f"{r['kind']:<10} {r['name']:<40} {r['at']}"
        + (f"  — {r['doc']}" if r["doc"] else ""),
    )


def children_of(g):
    kids: dict[str, list[str]] = {}
    for k, n in g["nodes"].items():
        if n["parent"]:
            kids.setdefault(n["parent"], []).append(k)
    return kids


def cmd_tree(g, a):
    start = a.arg.strip("/") or "."
    kids = children_of(g)
    if start == ".":
        roots = [k for k, n in g["nodes"].items() if n["parent"] is None]
    else:
        roots = [norm(g, start) if start not in g["nodes"] else start]
    rows = []

    def walk(k, depth):
        n = g["nodes"][k]
        rows.append(
            {"depth": depth, "kind": n["kind"], "id": k, "name": n["name"], "line": n.get("line")}
        )
        if depth < a.depth:
            for c in sorted(
                kids.get(k, []),
                key=lambda c: (g["nodes"][c]["kind"] != "dir", g["nodes"][c].get("line", 0), c),
            ):
                walk(c, depth + 1)

    for r in sorted(roots):
        walk(r, 0)
    emit(
        rows,
        a.json,
        lambda r: "  " * r["depth"]
        + f"{r['name']}{'/' if r['kind'] == 'dir' else ''}"
        + (f"  [{r['kind']} L{r['line']}]" if r["kind"] not in ("dir", "file") else ""),
    )


def cmd_parents(g, a):
    f = norm(g, a.arg)
    emit(g["nodes"][f]["imported_by"], a.json, str)


def cmd_children(g, a):
    f = norm(g, a.arg)
    emit(g["nodes"][f]["imports"], a.json, str)


def cmd_impact(g, a):
    f = norm(g, a.arg)
    seen, frontier, depth_of = {f}, [f], {f: 0}
    while frontier:
        nxt = []
        for x in frontier:
            for p in g["nodes"][x]["imported_by"]:
                if p not in seen:
                    seen.add(p)
                    depth_of[p] = depth_of[x] + 1
                    nxt.append(p)
        frontier = nxt
    rows = sorted(
        (
            {"file": k, "hops": d, "test": g["nodes"][k]["test"]}
            for k, d in depth_of.items()
            if k != f
        ),
        key=lambda r: (r["hops"], r["file"]),
    )
    emit(rows, a.json, lambda r: f"{r['hops']}  {r['file']}{'  (test)' if r['test'] else ''}")
    if not a.json:
        print(f"-- {len(rows)} dependents ({sum(r['test'] for r in rows)} tests) of {f}")


def cmd_outline(g, a):
    f = norm(g, a.arg)
    rows = sorted((n for n in g["nodes"].values() if n.get("file") == f), key=lambda n: n["line"])
    emit(
        [
            {
                "kind": n["kind"],
                "id": n["id"].split("::", 1)[1],
                "line": n["line"],
                "refs": n.get("refs"),
            }
            for n in rows
        ],
        a.json,
        lambda r: f"L{r['line']:<5} {r['kind']:<10} {r['id']}",
    )


def _match(term, *vals):
    return not term or any(term.lower() in str(v).lower() for v in vals)


def cmd_routes(g, a):
    emit(
        [r for r in g["routes"] if _match(a.arg, r["path"], r["handler"])],
        a.json,
        lambda r: f"{r['method']:<7} {r['path']:<45} {r['handler']}",
    )


def cmd_graphql(g, a):
    emit(
        [r for r in g["graphql"] if _match(a.arg, r["field"], r["resolver"])],
        a.json,
        lambda r: f"{r['op']:<12} {r['field']:<36} {r['resolver']}",
    )


def _config_text() -> str:
    out = subprocess.run(
        ["git", "ls-files", *CONFIG_GLOBS, *[f"**/{p}" for p in CONFIG_GLOBS]],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.split()
    return "\n".join(
        (ROOT / p).read_text(errors="replace")
        for p in set(out)
        if (ROOT / p).is_file()
        and (ROOT / p).stat().st_size < 400_000
        and "baseline" not in p
        and not p.startswith("docs/")
    )


def cmd_orphans(g, a):
    cfg = _config_text()
    rows = []
    for k, n in g["nodes"].items():
        if n["kind"] != "file" or n["imported_by"] or n["test"]:
            continue
        if any(fnmatch.fnmatch(k, p) for p in ENTRY_PATTERNS):
            continue
        no_ext = str(Path(k).with_suffix(""))
        dotted = no_ext.split("/", 1)[-1].replace("/", ".")  # backend/app/x/y.py -> app.x.y
        parts = k.split("/")
        suffixes = (
            "/".join(parts[i:]) for i in range(1, len(parts))
        )  # config/jest/x.js, jest.setup.js
        if (
            no_ext in cfg
            or (k.endswith(".py") and dotted in cfg)
            or any("/" + sfx in cfg for sfx in suffixes)
        ):
            continue
        rows.append({"file": k, "loc": n["loc"]})
    rows.sort(key=lambda r: -r["loc"])
    emit(rows, a.json, lambda r: f"{r['loc']:>6}  {r['file']}")
    if not a.json:
        print(
            f"-- {len(rows)} candidate orphan files, {sum(r['loc'] for r in rows)} lines. Verify before deleting."
        )


def cmd_unused(g, a):
    rows = []
    for n in g["nodes"].values():
        if (
            n["kind"] in {"dir", "file", "method"}
            or n["refs"] > 1
            or (a.arg and not n["file"].startswith(a.arg))
        ):
            continue
        if (
            n.get("decorated")
            or g["nodes"][n["file"]]["test"]
            or n["name"].startswith("__")
            or n["name"] in {"main", "default"}
        ):
            continue
        parent = g["nodes"][n["parent"]]
        if parent["kind"] != "file":  # nested in a class: only module-level symbols
            continue
        rows.append(
            {"symbol": n["name"], "kind": n["kind"], "at": loc(n), "test_refs": n["test_refs"]}
        )
    rows.sort(key=lambda r: r["at"])
    emit(
        rows,
        a.json,
        lambda r: f"{r['kind']:<10} {r['symbol']:<40} {r['at']}"
        + ("  (tests only)" if r["test_refs"] else ""),
    )
    if not a.json:
        print(
            f"-- {len(rows)} symbols referenced only at their definition (names are matched textually; verify)"
        )


def cmd_cycles(g, a):
    graph = {k: n["imports"] for k, n in g["nodes"].items() if n["kind"] == "file"}
    index, low, stack, on, comps, i = {}, {}, [], set(), [], [0]
    sys.setrecursionlimit(10000)

    def strong(v):
        index[v] = low[v] = i[0]
        i[0] += 1
        stack.append(v)
        on.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                comps.append(sorted(comp))

    for v in graph:
        if v not in index:
            strong(v)
    emit(comps, a.json, lambda c: f"[{len(c)}] " + " <-> ".join(c))


def cmd_stats(g, a):
    files = [n for n in g["nodes"].values() if n["kind"] == "file" and not n["test"]]
    kinds = Counter(n["kind"] for n in g["nodes"].values())
    out = {
        "built_at": g["built_at"],
        "git_head": g["git_head"],
        "nodes": dict(kinds),
        "largest_files": [(n["id"], n["loc"]) for n in sorted(files, key=lambda n: -n["loc"])[:10]],
        "most_imported": [
            (n["id"], len(n["imported_by"]))
            for n in sorted(files, key=lambda n: -len(n["imported_by"]))[:10]
        ],
        "most_dependencies": [
            (n["id"], len(n["imports"]))
            for n in sorted(files, key=lambda n: -len(n["imports"]))[:10]
        ],
    }
    if a.json:
        print(json.dumps(out, indent=1))
        return
    print(f"graph @ {out['git_head']} built {out['built_at']}: {out['nodes']}")
    for key in ("largest_files", "most_imported", "most_dependencies"):
        print(f"\n{key}:")
        for f, v in out[key]:
            print(f"  {v:>6}  {f}")


def cmd_guide(g, a):
    target = Path(a.arg or ".")
    chain = []
    for depth in range(len(target.parts) + 1):
        d = Path(*target.parts[:depth]) if depth else Path(".")
        if (ROOT / d / "AGENTS.md").is_file() and (ROOT / d).is_dir():
            chain.append(str(d / "AGENTS.md"))
    emit(chain, a.json, str)


COMMANDS = {
    "find": cmd_find,
    "tree": cmd_tree,
    "parents": cmd_parents,
    "children": cmd_children,
    "impact": cmd_impact,
    "outline": cmd_outline,
    "routes": cmd_routes,
    "graphql": cmd_graphql,
    "orphans": cmd_orphans,
    "unused": cmd_unused,
    "cycles": cmd_cycles,
    "stats": cmd_stats,
    "guide": cmd_guide,
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("command", choices=COMMANDS)
    ap.add_argument("arg", nargs="?", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-d", "--depth", type=int, default=2)
    ap.add_argument("-n", "--limit", type=int, default=40)
    a = ap.parse_args()
    COMMANDS[a.command](load(), a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
