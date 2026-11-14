# Contributing Guide for Agents

Last verified against code on **May 1, 2026**.

This guide defines how agents should make safe, reviewable changes in Manifest.

## 0. Context for AI-assisted work

Use **short, task-specific prompts** per `docs/PROMPT_TEMPLATE.md`. Product vision is `docs/PRODUCT_VISION.md`; stack and boundaries are root `AGENTS.md` and `docs/ARCHITECTURE_REFERENCE.md`; Cursor-wide defaults are `.cursor/rules/manifest-project.mdc`. Avoid pasting a long mega-prompt each session — that duplicates these sources and burns context.

## 1. Before You Change Code

1. Identify the owning files using `docs/AGENT_PLAYBOOK.md`.
2. Confirm whether change is GraphQL, REST, UI, or service-layer.
3. Check for async/background implications (`runBackgroundTasks`, Socket.IO, threaded jobs).
4. Check for auth implications (session JWT vs API key).

## 2. Change Checklist

For any feature/API change:

1. Update backend implementation.
2. Update frontend operation/component wiring (if applicable).
3. Update docs in `docs/`.
4. Add/update tests for changed behavior.
5. Run targeted validation commands.

## 3. Validation Commands

### Targeted vs full CI

- **Small or localized changes**: run **targeted** tests (specific `pytest` path or Jest pattern) plus manual smoke if UI-related.
- **Features touching GraphQL, auth, payments, or cross-cutting flows**: run **full** backend and frontend test suites locally before merge.
- **Definition of “green” for shipping**: `python3 scripts/check.py` passes (it checks the areas you changed; add `--all` before risky merges). There is no CI test gate, so this local run is the gate.

### Backend

```bash
cd backend
source .venv/bin/activate
pytest -q
```

Or use project script:

```bash
cd /Users/mihir/Projects/Manifest/backend
./run_tests.sh
```

### Frontend

```bash
cd /Users/mihir/Projects/Manifest/frontend
npm test
```

### Manual smoke checks

- `GET http://localhost:8000/ping`
- `POST http://localhost:8000/graphql` basic query
- App flows in `http://localhost:3000`

## 4. API Contract Discipline

### GraphQL

- Keep operation names stable unless a breaking change is explicitly intended.
- Ensure Strawberry type fields map correctly from DB naming to GraphQL naming.
- Never assume empty string updates should overwrite content; check resolver guardrails.

### REST

- Return consistent JSON structures and status codes.
- For `/api/v1/*`, preserve API key auth behavior and usage tracking semantics.
- Document new endpoints in `docs/API.md`.

## 5. Frontend State Discipline

Current app state pattern:

- Network state: Apollo cache
- Local app state: Apollo reactive vars (`localState.ts`)

When changing UI logic:

- Keep `userVar`, `accountVar`, `sidebarVar`, `similarIdeasVar` in sync with data flow.
- Avoid reintroducing stale Redux slice assumptions.

## 6. Common Failure Modes

- Overwriting idea description with empty HTML (blocked by resolver)
- Triggering too many background tasks from editor typing
- Editing `manifest_manager_refactored.py` expecting runtime changes (main imports `manifest_manager.py`)

## 7. Definition of Done

A change is done when:

1. Runtime behavior works end-to-end.
2. Relevant automated tests pass.
3. No new auth/security regressions introduced.
4. Docs in `docs/` reflect the new behavior.
5. Change can be traced quickly by another agent without reverse engineering.

## 8. Commits, pushes, and releases

Every push to `main` is expected to cut a SemVer GitHub Release via `.github/workflows/auto-release.yml`. Phrase commit subjects as Conventional Commits so the workflow can decide the bump and categorize the release notes:

| Prefix | Bump | Section in release notes |
| --- | --- | --- |
| `feat:` / `feat(<scope>):` | minor | 🚀 Features |
| `feat!:` / `BREAKING CHANGE:` in body | **major** | ⚠️ Breaking changes |
| `fix:` / `fix(<scope>):` | patch | 🐛 Bug fixes |
| `fix(security):` / `security:` | patch | 🔒 Security |
| `perf:` | patch | ⚡ Performance |
| `refactor:` | patch | 🧹 Refactors |
| `revert:` | patch | ⏪ Reverts |
| `chore(deps):` / `chore(deps-dev):` | patch | 📦 Dependencies |
| `chore:` / `docs:` / `test:` / `ci:` / `build:` / `style:` | — | _no release cut_ |

Guidelines:

- **Split mixed changes** into separate commits — one feature, one fix, one security patch. The categorizer is per-commit, not per-push, so a single mixed commit lands in only one section.
- **Add `[skip release]`** to the subject if you want a release-eligible push to skip the cut (e.g. coordinated multi-push work where only the final push should cut a tag).
- **Use signed tags** (`git tag -s vX.Y.Z`) for cuts that need SLSA L3 / SBOM / Cosign — that triggers `.github/workflows/release.yml`. The auto-release workflow only cuts lightweight tags.
- **Never hand-edit** tags or releases produced by the auto-release workflow. Push a follow-up `revert:` commit instead, which itself bumps the patch and produces a new release.
- The full agent-facing rule (with the in-CI workflow reference) lives in `AGENTS.md` § "Release cadence — every push to `main` cuts a SemVer release".
