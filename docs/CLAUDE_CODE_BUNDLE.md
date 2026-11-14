# Claude Code skill bundle for Manifest

This document is the canonical inventory of Claude Code skills, plugins, MCP servers, and hook
wiring used to develop Manifest. Apply it when onboarding a new contributor or fresh dev
machine.

The bundle is organized to enforce three product principles in every change: **easy to use**,
**robust**, **inexpensive to run and maintain**.

---

## 1. Skills loaded by default

Anthropic-shipped skills already available in this environment — keep enabled:

- `simplify` — post-edit pass for reuse and quality
- `security-review` — pre-PR scan of staged diff for auth/secret/injection regressions
- `review` — full PR review (branch or PR#)
- `init` — refresh `CLAUDE.md` after architectural shifts
- `claude-api` — tune prompt caching, model choice, cost on the AI Layer
- `fewer-permission-prompts` — populate `.claude/settings.json` allowlist from past transcripts
- `update-config` — author hooks/settings safely
- `loop` / `schedule` / `anthropic-skills:schedule` — recurring dev tasks
- `anthropic-skills:consolidate-memory` — periodic merge of duplicate / stale memory
- `anthropic-skills:skill-creator` — author new repo-local skills
- `anthropic-skills:pdf` / `docx` / `pptx` / `xlsx` — match Manifest's AI artifact surface

## 2. Plugins to install from the marketplace

Run `/plugin marketplace add anthropics/claude-code` then `/plugin install <name>` for each.

| Phase | Skill / Plugin (search term) | Purpose |
| --- | --- | --- |
| Code | `python-formatter` (ruff/black bundle) | Backend lint & format |
| Code | `mypy-typing` | Backend gradual typing |
| Code | `typescript-strict-migrator` | Frontend stricter TS |
| Code | `graphql-schema-guard` | Protect Strawberry schema |
| Test | `test-generator-pytest` | Auto-draft pytest from diffs |
| Test | `test-generator-jest` | Jest tests for changed components |
| Test | `cypress-author` | E2E specs for changed user journeys |
| Test | `mutation-testing` | mutmut/Stryker on critical paths |
| Test | `flaky-test-detective` | Cypress + socket.io flake patrol |
| Security | `owasp-top10-review` | Layer over `security-review` |
| Security | `auth-flow-review` | Marketplace + investor flows |
| Security | `input-validation-review` | API surface and form intake |
| Security | `dependency-audit` | npm audit + pip-audit wrapper |
| Security | `secret-scan-extender` | gitleaks + trufflehog |
| Security | `supabase-migration-safety` | Lock and rewrite analysis |
| UX | `a11y-audit` (axe-core) | WCAG sweep on changed components |
| UX | `lighthouse-runner` | Perf budget enforcement |
| UX | `tailwind-cleanup` | Remove dead utility classes |
| UX | `design-system-enforcer` | Centralized design patterns rule |
| AI Layer | `prompt-cache-optimizer` | Cache control on every prompt |
| AI Layer | `llm-cost-monitor` | OpenAI/Gemini/Perplexity spend tracking |
| AI Layer | `eval-harness` | Regression eval for AI artifacts |
| Docs | `docstring-generator` | Backend docstrings on public APIs |
| Docs | `openapi-spec-sync` | Keep `docs/API.md` in step with routes |
| Docs | `changelog-from-commits` | Auto-changelog from PR titles |
| DevOps | `github-actions-optimizer` | Cache-hit + matrix improvements |
| DevOps | `dockerfile-linter` | Image-size and security wins |

If a plugin is not yet on the public marketplace, author a local equivalent via
`anthropic-skills:skill-creator` and place it under `.claude/skills/` (see section 4).

## 3. MCP servers

Install via `/mcp add <name>`:

- **GitHub MCP** — read PRs, issues, runs without shelling `gh` each time
- **Postgres / Supabase MCP** — inspect schema and run safe read queries during planning
- **Sentry MCP** — pull live error signatures into bug-fix sessions
- **Playwright / Browser MCP** — drive Cypress-like flows for UX skills
- **Linear** or **Jira MCP** — thread tickets → spec → code → PR loop
- **Filesystem MCP** — scoped read of `docs/` for cross-file synthesis

Source list: <https://github.com/modelcontextprotocol/servers>.

## 4. Custom Manifest skills (`.claude/skills/`)

These five skills are repo-local. They encode constraints unique to Manifest and are
authored as text-only SKILL.md files in this repository. Each fires on the matching
filesystem patterns wired up in section 5.

- `manifest-agent-playbook-check` — verify file is owned by the right agent per `AGENT_PLAYBOOK.md`
- `manifest-guest-session-guard` — flag changes to guest-TTL/merge logic without tests
- `manifest-pitch-reel-cost-guard` — block growth in Veo/Gemini calls without cache or feature flag
- `manifest-graphql-resolver-template` — scaffold resolver + service-layer pair + test
- `manifest-docs-sync` — when public contract changes (GraphQL, REST, env), require `docs/` edit

## 5. Proposed `.claude/settings.json`

The Claude Code runtime guards self-modification of its own settings. Review the JSON
below and apply manually with:

```sh
cp docs/CLAUDE_CODE_BUNDLE_settings.json .claude/settings.json
```

The proposed JSON is kept in `docs/CLAUDE_CODE_BUNDLE_settings.json` so it can be reviewed
in diff form without granting Claude write access to the live config.

Hook coverage:

- `PostToolUse(Edit|Write|MultiEdit)` — emits a contextual hint based on which file was touched (backend Python, frontend component, supabase migration, AI Layer, auth/security/payment/legal, GraphQL schema, guest_session).
- `Stop` — checks staged diff at end of turn; emits gate hints if sensitive files or public contracts were changed without `/security-review` or `manifest-docs-sync`.

Hooks are advisory (echo-only). They never block or rewrite code. They surface reminders
so the agent invokes the right skill on the right file.

## 6. Phased install order

1. **Day 1 — Foundation**: apply `.claude/settings.json` from section 5; install ruff/black/mypy via pre-commit (already wired in `.pre-commit-config.yaml`); add backend `pyproject.toml`.
2. **Day 2 — Security spine**: `owasp-top10-review`, `auth-flow-review`, `dependency-audit`, `supabase-migration-safety`, secret-scan extension.
3. **Day 3 — AI cost & quality**: `prompt-cache-optimizer`, `llm-cost-monitor`, `eval-harness` against existing prompts in `backend/app/prompts/`.
4. **Day 4 — UX & a11y**: `a11y-audit`, `lighthouse-runner`, `tailwind-cleanup`.
5. **Day 5 — Test depth**: test-generator skills + `mutation-testing` on auth/legal/payment paths.
6. **Day 6 — Custom Manifest skills**: confirm `.claude/skills/manifest-*` are loading and trigger on correct patterns.
7. **Day 7 — MCP wiring**: GitHub + Supabase + Sentry MCPs.

## 7. Verification

1. `/plugin list` — every skill in section 1 + 2 is loaded.
2. Touch a `backend/app/services/ai_*.py` file → PostToolUse hook prints the AI Layer hint.
3. Edit a `supabase/migrations/*.sql` file → hook flags the migration safety requirement.
4. Stage a fake `AKIA...` secret → gitleaks pre-commit blocks before commit.
5. Modify `backend/app/graphql/schema.py` → Stop hook reminds to run `manifest-docs-sync`.
6. Run `/security-review` on a synthetic auth-bypass branch → must flag the bypass.
7. Add a prompt without `cache_control` → `prompt-cache-optimizer` flags in PR review.
8. CI: `ruff`, `mypy`, `pip-audit`, `npm audit`, Lighthouse CI, size-limit all gate the PR.

If all eight pass, the bundle is wired correctly and Claude *actively uses* these skills
during development rather than just having them installed.
