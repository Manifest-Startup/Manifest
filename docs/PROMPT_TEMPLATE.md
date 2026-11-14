# Short task prompt template (AI-assisted work)

Use this **per task** instead of pasting a long “mega-prompt.” **Canonical AI agent guidance** lives in `docs/AI_AGENT_BASE_PROMPT.md`; **product vision** lives in `docs/PRODUCT_VISION.md`; **architecture and agents** in root `AGENTS.md` and `docs/ARCHITECTURE_REFERENCE.md`; **defaults for Cursor** in `.cursor/rules/manifest-project.mdc`.

Copy the block below and fill in the brackets.

---

## Template

**Goal**  
[One or two sentences: what should work for the user when we are done?]

**Acceptance criteria**  
- [ ] [Observable outcome 1]  
- [ ] [Observable outcome 2]

**Scope**  
- In scope: [files/areas or “backend only”, “UI only”, etc.]  
- Out of scope / do not change: [migrations, unrelated features, etc.]

**Surfaces & risks** (check what applies)  
- [ ] GraphQL / `schema.py`  
- [ ] Auth / sessions / guests (`_require_full_account`, etc.)  
- [ ] Socket.IO or background jobs  
- [ ] Pitch reels / messaging / other domain: [name]

**Tests** (proportionate — `python3 scripts/check.py` must pass)  
- [ ] Targeted: `pytest path/to/test` and/or `npm test -- --testPathPattern=...`  
- [ ] Broader: full backend/frontend suites before merge if the change is risky  
- [ ] E2E (Cypress): only if user flows or critical paths changed  
- [ ] Performance: only if this change is performance-sensitive  

**Docs** (only if contracts or public behavior changed)  
- [ ] `docs/API.md` and/or other `docs/*` as needed — not every cosmetic edit.

**Commit + release**  
- [ ] Conventional Commit subject (`feat:` / `fix:` / `fix(security):` / `perf:` / `chore(deps):` / `chore:` / `docs:` / `ci:` / `refactor:` / `revert:`). Use `!` or `BREAKING CHANGE:` for breaking changes.  
- [ ] Push to `main` will auto-cut a release via `.github/workflows/auto-release.yml` — confirm the prefix matches the change. Add `[skip release]` only if intentionally skipping. Full rule: `AGENTS.md` § "Release cadence — every push to `main` cuts a SemVer release".

**Notes**  
[Any links to issues, screenshots, or constraints.]

---

## Why not a mega-prompt every time?

Long repeated prompts cost context, duplicate what is already in the repo, and encourage unrealistic expectations (e.g. “run every test type on every edit”). Keep **base guidance** in `docs/AI_AGENT_BASE_PROMPT.md`, **invariants** in **project rules**, and **vision** in **docs**; keep **chat** for the specific task above.
