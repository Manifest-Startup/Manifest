# Manifest — agent guide (root)

From a rough idea to an investable plan, in one workspace. This is the **parent** guide: rules here apply everywhere. Each subsystem has a **child** guide with its own commands and gotchas; read the child before editing inside it.

| Child guide | Owns |
|---|---|
| [`backend/AGENTS.md`](backend/AGENTS.md) | FastAPI + Strawberry GraphQL API, services, security, workers |
| [`frontend/AGENTS.md`](frontend/AGENTS.md) | Vite + React + TypeScript app (Apollo Client) |
| [`deploy/cloudflare/AGENTS.md`](deploy/cloudflare/AGENTS.md) | Production edge Worker (static assets + backend proxy) |
| [`mcp_server/AGENTS.md`](mcp_server/AGENTS.md) | Manifest MCP server for external agents |

Product intent and long-form context: `docs/AI_AGENT_BASE_PROMPT.md`, `docs/PRODUCT_VISION.md`, `docs/CONTRIBUTING_AGENTS.md`, `ARCHITECTURE.md`; the Claude Code skill/plugin/MCP bundle is `docs/CLAUDE_CODE_BUNDLE.md`. Repo skills in `.claude/skills/manifest-*` encode guardrails (guest sessions, AI cost, GraphQL templates, docs sync); use the matching one when you touch that surface.

## Find code before reading it

1. **Code graph** — `python3 scripts/codegraph/query.py <command>` (auto-rebuilds when sources change, ~1 s):
   - `find <name>` symbol/file lookup · `outline <file>` symbols with lines · `tree <dir> -d 2` parent→child structure
   - `parents <file>` who imports it · `children <file>` what it imports · `impact <file>` transitive blast radius (+ tests)
   - `routes [term]` REST → handler · `graphql [term]` GraphQL field → resolver
   - `orphans` / `unused [path]` dead-code candidates · `cycles` import cycles · `stats` hot spots. Add `--json` for tooling.
2. **LSP** — go-to-definition / find-references / call hierarchy. `pyrightconfig.json` and `frontend/tsconfig.json` make every import resolve; Python needs `uv venv .venv && uv pip install -r backend/requirements.txt -e mcp_server`.
3. `rg` for strings and config. Read line ranges, not whole files: `backend/app/graphql/schema.py` alone is ~6k lines.

## Engineering rules

- Keep changes inside the requested feature. Prefer extending an existing helper over adding a parallel one (check `find`/`impact` first); remove code you make dead in the same change and confirm with `orphans`/`unused`.
- One owner per concern: OpenAI keys (bring your own key) → `backend/app/services/ai_credentials.py` (never read `OPENAI_API_KEY` directly), cookies → `backend/app/security/cookies.py`, DB access → `backend/app/db/`, GraphQL documents → `frontend/src/features/core/apollo/queries.ts`.
- Defaults for every feature: very easy to use, robust, cheap to run, few primary actions, proportionate tests, docs updated when behaviour or a public contract changes.
- Never commit credentials, customer records, production data, virtualenvs, coverage or build output (see `.gitignore`).
- Do not run deployments or database migrations unless the task explicitly asks.

## Commits and releases

Every push to `main` cuts a SemVer GitHub Release (`.github/workflows/auto-release.yml`), so commit subjects are Conventional Commits: `feat:` minor · `fix:` / `perf:` / `refactor:` / `revert:` / `chore(deps):` patch · `feat!:` or `BREAKING CHANGE:` major · `chore:` / `docs:` / `test:` / `ci:` / `build:` / `style:` no release. Use `fix(security):` for security patches and add `[skip release]` to opt a push out. Signed tags (`git tag -s vX.Y.Z`) are only for the SLSA/SBOM pipeline in `release.yml` (`docs/security/RELEASE_PLAYBOOK.md`). The hourly Autopilot loop opens PRs into the `autopilot` branch only and may not edit workflows, `auth/`, `security/`, `config/` or its own scripts (`docs/AUTOPILOT.md`).

## Checks (local only; there is no CI test gate)

`python3 scripts/check.py` runs the checks for the areas you changed (vs `origin/main`, including uncommitted files): ruff lint+format, the backend pytest suite, Jest `--findRelatedTests` + `tsc` + ESLint, the edge Worker, MCP server and tooling tests. `--all` checks everything (~80 s); `--only backend frontend` narrows it; `--install-hook` runs it before every `git push` (skip once with `--no-verify`). Every suite is green, so any failure is real: fix it before pushing.

Setup once: `uv venv .venv && uv pip install -r backend/requirements.txt -e mcp_server -e .` and `cd frontend && npm ci`. GitHub only runs releases, deploy-adjacent automation (Autopilot, merge train, scheduled production smoke tests) and the security scanner suite for signed releases.
