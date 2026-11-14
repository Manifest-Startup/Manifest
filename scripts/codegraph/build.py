#!/usr/bin/env python3
"""Build the Manifest code knowledge graph into .codegraph/graph.json.

The graph has three layers:

* containment (parent -> child): dir -> file -> class -> method/function
* dependencies: file -> file import edges (Python AST + TS/JS import scan)
* surface: FastAPI routes, Strawberry GraphQL fields and a symbol reference index

Usage:
    python3 scripts/codegraph/build.py              # rebuild
    python3 scripts/codegraph/build.py --if-stale   # rebuild only when sources changed
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / ".codegraph"
OUT_FILE = OUT_DIR / "graph.json"
SCHEMA_VERSION = 1

PY_EXT = {".py"}
TS_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
SKIP_PARTS = {"node_modules", "dist", "build", "coverage", "generated", "__pycache__", ".venv"}

# Python import roots: top-level package directory -> folder that contains it.
PY_ROOTS = ["backend", "backend/scripts", "mcp_server/src", "src", "."]

# TypeScript resolution, mirrors frontend/tsconfig.json (baseUrl "src").
TS_BASE = "frontend/src"
TS_RESOLVE_SUFFIXES = [
    "",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    "/index.ts",
    "/index.tsx",
    "/index.js",
]

IMPORT_RE = re.compile(
    r"""(?:^|\s)(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]"""
    r"""|(?:^|\s)import\s*['"]([^'"]+)['"]"""
    r"""|import\(\s*['"]([^'"]+)['"]\s*\)"""
    r"""|require\(\s*['"]([^'"]+)['"]\s*\)""",
    re.M,
)
TS_DECL_RE = re.compile(
    r"^(export\s+(?:default\s+)?)?(?:async\s+)?(function|class|const|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
    re.M,
)
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "websocket", "api_route"}


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    keep = []
    for rel in out.splitlines():
        p = Path(rel)
        if p.suffix not in PY_EXT | TS_EXT or SKIP_PARTS & set(p.parts) or rel.startswith("."):
            continue
        if rel.endswith((".min.js", ".d.ts")) or "/.venv" in rel:
            continue
        if (ROOT / rel).is_file():
            keep.append(rel)
    return sorted(keep)


def source_fingerprint(files: list[str]) -> str:
    newest = max(((ROOT / f).stat().st_mtime for f in files), default=0)
    return f"{len(files)}:{int(newest)}"


class GraphBuilder:
    def __init__(self, files: list[str]):
        self.files = files
        self.fileset = set(files)
        self.nodes: dict[str, dict] = {}
        self.imports: dict[str, set[str]] = {}
        self.routes: list[dict] = []
        self.graphql: list[dict] = []
        self.idents: Counter[str] = Counter()
        self.py_modules = self._index_python_modules()

    # ---- containment -------------------------------------------------
    def add_node(self, node_id: str, kind: str, name: str, parent: str | None, **extra) -> None:
        self.nodes[node_id] = {"id": node_id, "kind": kind, "name": name, "parent": parent, **extra}

    def ensure_dirs(self, rel: str) -> str:
        parent = None
        parts = Path(rel).parts[:-1]
        for i in range(len(parts)):
            d = "/".join(parts[: i + 1])
            if d not in self.nodes:
                self.add_node(d, "dir", parts[i], parent)
            parent = d
        return parent or "."

    # ---- python --------------------------------------------------------
    def _index_python_modules(self) -> dict[str, str]:
        mods: dict[str, str] = {}
        for rel in self.files:
            if not rel.endswith(".py"):
                continue
            for root in PY_ROOTS:
                prefix = "" if root == "." else root + "/"
                if not rel.startswith(prefix):
                    continue
                mod = rel[len(prefix) : -3].replace("/", ".")
                if mod.endswith(".__init__"):
                    mod = mod[: -len(".__init__")]
                mods.setdefault(mod, rel)
        return mods

    def _resolve_py(self, rel: str, module: str | None, level: int, names: list[str]) -> set[str]:
        if level:
            base = Path(rel).parent
            for _ in range(level - 1):
                base = base.parent
            pkg_rel = str(base)
            candidates = [f"{pkg_rel}/{module.replace('.', '/')}" if module else pkg_rel]
            hits = set()
            for c in candidates:
                for n in [None, *names]:
                    path = f"{c}/{n}" if n else c
                    for p in (path + ".py", path + "/__init__.py"):
                        if p in self.fileset:
                            hits.add(p)
            return hits
        hits = set()
        if not module:
            return hits
        for n in names:
            if f"{module}.{n}" in self.py_modules:
                hits.add(self.py_modules[f"{module}.{n}"])
        if module in self.py_modules:
            hits.add(self.py_modules[module])
        return hits

    def parse_python(self, rel: str, text: str) -> None:
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            return
        deps: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    deps |= self._resolve_py(rel, a.name, 0, [])
            elif isinstance(node, ast.ImportFrom):
                deps |= self._resolve_py(rel, node.module, node.level, [a.name for a in node.names])
        deps.discard(rel)
        self.imports[rel] = deps
        self._prefixes = _router_prefixes(tree)
        self._walk_py_defs(rel, tree.body, rel, None)

    def _walk_py_defs(self, rel: str, body: list, parent: str, owner: str | None) -> None:
        for node in body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):  # noqa: UP038 (py3.9)
                continue
            is_class = isinstance(node, ast.ClassDef)
            kind = "class" if is_class else ("method" if owner else "function")
            qual = f"{owner}.{node.name}" if owner else node.name
            node_id = f"{rel}::{qual}"
            doc = (ast.get_docstring(node) or "").strip().splitlines()
            self.add_node(
                node_id,
                kind,
                node.name,
                parent,
                file=rel,
                line=node.lineno,
                end=getattr(node, "end_lineno", node.lineno),
                doc=doc[0][:160] if doc else "",
                decorated=bool(node.decorator_list),
            )
            self._collect_surface(rel, node, qual, owner)
            if is_class:
                self._walk_py_defs(rel, node.body, node_id, qual)

    def _collect_surface(self, rel: str, node, qual: str, owner: str | None) -> None:
        for dec in getattr(node, "decorator_list", []):
            call = dec if isinstance(dec, ast.Call) else None
            func = call.func if call else dec
            if not isinstance(func, ast.Attribute):
                continue
            target = ast.unparse(func.value)
            if (
                func.attr in ROUTE_METHODS
                and call
                and call.args
                and isinstance(call.args[0], ast.Constant)
            ):
                path = self._prefixes.get(target, "") + call.args[0].value
                self.routes.append(
                    {
                        "method": func.attr.upper(),
                        "path": path,
                        "handler": f"{rel}::{qual}",
                        "line": node.lineno,
                    }
                )
            elif target.startswith("strawberry") and func.attr in {
                "field",
                "mutation",
                "subscription",
            }:
                op = {"field": "query", "mutation": "mutation", "subscription": "subscription"}[
                    func.attr
                ]
                self.graphql.append(
                    {
                        "op": op,
                        "field": _camel(node.name),
                        "type": owner,
                        "resolver": f"{rel}::{qual}",
                        "line": node.lineno,
                    }
                )

    # ---- typescript ------------------------------------------------------
    def _resolve_ts(self, rel: str, spec: str) -> str | None:
        if spec.startswith("."):
            base = os.path.normpath(f"{Path(rel).parent.as_posix()}/{spec}")
        elif rel.startswith("frontend/"):
            base = f"{TS_BASE}/{spec}"
        else:
            return None
        for suf in TS_RESOLVE_SUFFIXES:
            if base + suf in self.fileset:
                return base + suf
        return None

    def parse_ts(self, rel: str, text: str) -> None:
        deps = set()
        for m in IMPORT_RE.finditer(text):
            spec = next(g for g in m.groups() if g)
            hit = self._resolve_ts(rel, spec)
            if hit and hit != rel:
                deps.add(hit)
        self.imports[rel] = deps
        for m in TS_DECL_RE.finditer(text):
            exported, kw, name = m.group(1), m.group(2), m.group(3)
            if kw == "const" and not (exported or name[:1].isupper()):
                continue
            kind = (
                "component"
                if kw in {"function", "const"} and name[:1].isupper() and rel.endswith(("x",))
                else kw
            )
            line = text.count("\n", 0, m.start()) + 1
            self.add_node(
                f"{rel}::{name}", kind, name, rel, file=rel, line=line, exported=bool(exported)
            )

    # ---- driver --------------------------------------------------------
    def build(self) -> dict:
        for rel in self.files:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
            parent = self.ensure_dirs(rel)
            lang = "python" if rel.endswith(".py") else "ts"
            self.add_node(
                rel,
                "file",
                Path(rel).name,
                parent,
                lang=lang,
                loc=text.count("\n") + 1,
                test=_is_test(rel),
            )
            if not _is_test(rel):
                self.idents.update(IDENT_RE.findall(text))
            (self.parse_python if lang == "python" else self.parse_ts)(rel, text)
            if _is_test(rel):
                self.idents.update({f"test::{t}" for t in set(IDENT_RE.findall(text))})
        importers: dict[str, list[str]] = {}
        for src, deps in self.imports.items():
            for d in deps:
                importers.setdefault(d, []).append(src)
        for f, node in self.nodes.items():
            if node["kind"] == "file":
                node["imports"] = sorted(self.imports.get(f, ()))
                node["imported_by"] = sorted(importers.get(f, ()))
        for node in self.nodes.values():
            if node["kind"] not in {"dir", "file"}:
                node["refs"] = self.idents.get(node["name"], 0)
                node["test_refs"] = self.idents.get(f"test::{node['name']}", 0)
        return {
            "schema": SCHEMA_VERSION,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "git_head": _git_head(),
            "fingerprint": source_fingerprint(self.files),
            "nodes": self.nodes,
            "routes": sorted(self.routes, key=lambda r: (r["path"], r["method"])),
            "graphql": sorted(self.graphql, key=lambda g: (g["op"], g["field"])),
        }


def _camel(name: str) -> str:
    """Strawberry's default field naming: snake_case resolver -> camelCase field."""
    head, *rest = name.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


def _router_prefixes(tree: ast.Module) -> dict[str, str]:
    """Map module-level ``name = APIRouter(prefix="/x")`` assignments to their prefix."""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            callee = ast.unparse(node.value.func)
            if callee.endswith("APIRouter"):
                prefix = next(
                    (
                        k.value.value
                        for k in node.value.keywords
                        if k.arg == "prefix" and isinstance(k.value, ast.Constant)
                    ),
                    "",
                )
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        out[t.id] = prefix
    return out


def _is_test(rel: str) -> bool:
    name = Path(rel).name
    return (
        "/tests/" in f"/{rel}"
        or "/__tests__/" in rel
        or "cypress/" in rel
        or name.startswith("test_")
        or ".test." in name
        or ".spec." in name
        or ".stories." in name
    )


def _git_head() -> str:
    r = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    )
    return r.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument(
        "--if-stale", action="store_true", help="skip when the graph is already current"
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    files = tracked_files()
    if args.if_stale and OUT_FILE.exists():
        try:
            if json.loads(OUT_FILE.read_text()).get("fingerprint") == source_fingerprint(files):
                return 0
        except (json.JSONDecodeError, OSError):
            pass
    start = time.perf_counter()
    graph = GraphBuilder(files).build()
    OUT_DIR.mkdir(exist_ok=True)
    OUT_FILE.write_text(json.dumps(graph, separators=(",", ":")))
    if not args.quiet:
        kinds = Counter(n["kind"] for n in graph["nodes"].values())
        edges = sum(len(n.get("imports", ())) for n in graph["nodes"].values())
        print(
            f"codegraph: {dict(kinds)} | {edges} import edges | {len(graph['routes'])} routes | "
            f"{len(graph['graphql'])} graphql fields | {time.perf_counter() - start:.1f}s -> {OUT_FILE.relative_to(ROOT)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
