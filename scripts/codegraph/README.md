# Code graph

A local knowledge graph of the Manifest codebase for fast retrieval by people and coding agents. Standard library only; no install step.

```bash
python3 scripts/codegraph/query.py find SsoLogin          # where is it defined
python3 scripts/codegraph/query.py impact backend/app/security/cookies.py   # what breaks if I change it
python3 scripts/codegraph/query.py guide frontend/src/App.tsx               # which AGENTS.md files apply
python3 scripts/codegraph/query.py --help                 # all commands
```

## What it contains

`build.py` writes `.codegraph/graph.json` (git-ignored, rebuilt in about 1 s, automatically by `query.py` whenever a source file changes):

- **Containment tree (parent → child):** directory → file → class → method, and file → function/component/type. Every node has `parent`, so `tree` and `outline` walk it directly.
- **Dependencies:** file → file import edges from the Python AST (`app.*`, `manifest_mcp`, relative imports) and TS/JS `import`/`export from`/`import()`/`require` (relative and `baseUrl: src` paths). Each file node stores `imports` and `imported_by`.
- **API surface:** FastAPI routes (`@router.get(...)` etc.) and Strawberry GraphQL fields mapped to their handler.
- **Reference counts:** how often each symbol name appears in non-test code (`refs`) and tests (`test_refs`), used by `unused`.

## Limits

Name matching is textual, so `unused` and `orphans` are candidate lists: confirm with `rg` before deleting. Symbols registered by decorators, and files loaded by config (jest, Docker, workflows, `wrangler.jsonc`), entry points and `__mocks__` are excluded on purpose. Extend `ENTRY_PATTERNS` in `query.py` when a new kind of runtime-loaded file appears.

Tests: `python3 -m pytest tests/tooling/test_codegraph.py -q`.
