# Manifest Autopilot — 24/7 autonomous self-improvement loop

Autopilot is the v2 of Manifest's agent loop. Where the v1 bug-fix agent
(`run_bugfix_agent.py`) only *diagnoses* issues, Autopilot **closes the loop**:
it picks a high-value open issue, writes the fix with the OpenAI Codex CLI, verifies it
against the same checks `scripts/check.py` runs, and opens an auto-merging PR — but
**never against `main`** (which auto-releases on every push). It targets a
protected `autopilot` branch that you promote to `main` on your own cadence.

The only knob you manage is **spend**. A hard daily budget gate ($30/day by
default) makes every run a no-op once the day's cap is reached.

```
 cron (hourly)
      │
      ▼
┌─────────────────┐  off / over-budget   ┌──────────┐
│ kill switch +   │ ───────────────────► │ no-op    │
│ budget gate     │                      └──────────┘
└────────┬────────┘
         │ allowed
         ▼
   pick ONE issue ──► Codex CLI (headless) writes the change on a worktree
         │
         ▼
   guardrails: denylist + diff-size + ruff/pytest/jest (same as scripts/check.py)
         │ red? ─► feed failures back to Codex, re-check (up to N repairs) ─┐
         │ green                                                           │
         ▼                                                          (loops back)
   PR into `autopilot` ─► CI re-runs on the PR ─► auto-merge on green
         │
         ▼
   you promote `autopilot`→`main`; record spend + append JOURNAL.md
```

## Where work comes from

Autopilot does not invent work. It consumes the GitHub issues that the
existing cron loops already file, plus anything you label:

| Source | Workflow | Labels it files |
| --- | --- | --- |
| Live-site crawl (UX / a11y / SEO) | `website-testing.yml` | `website-audit`, `accessibility`, `seo` |
| Production smoke tests (Playwright) | `production-tests.yml` | `automated-test` |
| User survey themes | `survey-feedback.yml` | `enhancement` |
| Anything you want done | — | `autopilot`, `feature`, `bug`, `enhancement` |

Eligible labels: `automated-test`, `autopilot`, `feature`, `bug`,
`enhancement`, `website-audit`, `accessibility`, `seo`. Issues are ranked by
priority label (`priority:critical` → `priority:high` → `automated-test` →
`bug` → `accessibility` → …), and exactly one is picked per run. Security and
governance issues (`security-scan-failure`, `security-drift`, …) are **not**
eligible — they touch denylisted code and need a human. Add `autopilot:hard`
to route an issue to the stronger model; add `autopilot:skip` to make Autopilot
ignore one.

> Autopilot acts on **issues, not pull requests** — it never touches open PRs,
> including Dependabot dependency-bump PRs. For those, use Dependabot's own
> auto-merge, not this loop.

## One-time setup

1. **OpenAI key.** The Codex engine reads `OPENAI_API_KEY`, which the workflow
   wires from the org-level **`OPENAI_DEV_KEY`** secret — already available to
   this repo, so there is nothing to add. (Autopilot also reuses the existing
   `GITHUB_TOKEN` and `DATABASE_URL` secrets.) If you ever rename the org
   secret, update the `OPENAI_API_KEY:` line in both autopilot workflows.

2. **Create the `autopilot` branch** off `main`:
   ```bash
   git switch main && git pull
   git switch -c autopilot && git push -u origin autopilot
   ```

3. **Protect `autopilot`** so auto-merge waits for green. Repo → Settings →
   Branches → Add rule for `autopilot`: require status checks to pass, and
   leave required status checks empty: there is no CI test workflow any more; the loop's own pre-PR gate (`scripts/check.py`-equivalent ruff/pytest/jest) is the check.

4. **Turn it on.** Repo → Settings → Secrets and variables → Actions →
   **Variables** → `AUTOPILOT_ENABLED = true`.

5. *(optional)* Tune via repo **Variables** (all have safe defaults):

   | Variable | Default | Purpose |
   | --- | --- | --- |
   | `AUTOPILOT_ENABLED` | `false` | Master on/off. Anything but `true` = no-op. |
   | `AUTOPILOT_DAILY_USD` | `30` | Hard daily model-cost cap. |
   | `AUTOPILOT_PER_RUN_USD` | `3` | Advisory per-run ceiling passed to the engine. |
   | `AUTOPILOT_MODEL` | `gpt-5-codex` | Default Codex coding model (`autopilot:hard` issues use `gpt-5`). |
   | `AUTOPILOT_AUTOMERGE` | `false` | `true` enables `gh pr merge --auto`. |
   | `AUTOPILOT_REPAIR_ATTEMPTS` | `2` | Times to feed CI failures back to the engine to fix before giving up. |
   | `AUTOPILOT_MAX_FILES` | `12` | Reject diffs touching more files. |
   | `AUTOPILOT_MAX_LINES` | `600` | Reject diffs changing more lines. |

## Recommended rollout

Earn trust before running wide open:

1. **Shadow** — dispatch with `dry_run: true`. Autopilot selects, implements on
   a throwaway worktree, runs checks, and prints the diff/PR it *would* open.
   Open nothing. Eyeball quality for a few days.
2. **Gated** — set `AUTOPILOT_ENABLED=true`, leave `AUTOPILOT_AUTOMERGE=false`,
   `AUTOPILOT_DAILY_USD=10`. PRs open into `autopilot`; **you** click merge.
3. **Full auto** — `AUTOPILOT_AUTOMERGE=true`, `AUTOPILOT_DAILY_USD=30`. The
   hourly cron runs unattended. You promote `autopilot`→`main` when you like.

## Operating it

- **Pause instantly:** set `AUTOPILOT_ENABLED=false`. In-flight runs finish;
  no new run starts.
- **Change the budget:** edit `AUTOPILOT_DAILY_USD`. Takes effect next run.
- **Run it now:** Actions → *Autopilot* → *Run workflow* (optionally pin an
  `issue_number` or tick `dry_run`).
- **Promote to `main`** (the only step that releases):
  ```bash
  git switch main && git pull
  git merge --no-ff origin/autopilot      # review the combined diff first
  git push                                # each squashed commit cuts its release
  ```
  Because every push to `main` auto-releases, promote deliberately — review the
  accumulated `autopilot` diff as one batch, then push.
- **Read the journal:** `docs/autopilot/JOURNAL.md` — one line per run (issue,
  action, model, cost, PR). Spend is also in `agent_cost_events`
  (`agent_kind = 'autopilot'`); `cost_tracking_service.get_daily_spend` is what
  the budget gate reads.

## Safety model

- **Never touches `main`.** PRs target `autopilot`; releases stay human-gated.
- **Green before merge (self-healing CI).** Before a PR is opened, the loop
  runs the same `ruff`/`pytest`/`jest` gate as `scripts/check.py`; if it's red, it
  feeds the failure back to the engine to fix and re-checks, up to
  `AUTOPILOT_REPAIR_ATTEMPTS` times. The PR only opens once local checks pass,
  and (since CI was removed on 2026-11-14) nothing re-runs on the PR itself — `autopilot`'s branch protection
  requires those checks, so auto-merge waits for a genuine green CI.
- **Fail-closed budget gate.** If the cost ledger is unreachable, spend is
  treated as over-cap and the run no-ops — it cannot spend blind.
- **Denylist (no self-modification).** The loop's own rails are off-limits and
  any diff touching them is discarded: `.github/workflows/**`,
  `backend/app/auth/**`, `backend/app/security/**`, `backend/app/config/**`,
  `CODEOWNERS`, the autopilot/bugfix scripts, `docs/autopilot/**`, and the
  `manifest-*` guardrail skills.
- **Bounded blast radius.** Diff-size cap + single-issue-per-run + a
  `concurrency` group (one run at a time).
- **Repo conventions in the prompt.** The Codex engine reads `AGENTS.md`
  natively and is instructed to obey `CLAUDE.md` and
  `docs/AI_AGENT_BASE_PROMPT.md`. The denylist, diff-size, and full `scripts/check.py`
  CI run are the hard gates regardless of what the engine does.

## Limitations (be honest)

- GitHub Actions cron is discrete, not truly continuous — runs fire ~hourly and
  can be delayed under load. The budget gate, not the cron, governs spend.
- The per-run cap is advisory (passed into the engine's prompt); the **daily**
  cap is the hard enforcement boundary, checked before each run starts.
- **Budget accuracy depends on model pricing.** The daily cap is enforced
  against token cost priced by `cost_tracking_service.PRICING_USD_PER_1M`. That
  table is OpenAI-model based; for the Codex model you run, add its exact
  input/output per-1M pricing there so the cap is precise — unknown models use
  a conservative $1/$3 fallback. If Codex `--json` reports no token usage, the
  loop estimates from text length so the gate never sees a free run.
- **Codex CLI flags vary by version.** The workflow installs the latest
  `@openai/codex` and the orchestrator uses the documented full-automation
  flags (`codex exec --json --dangerously-bypass-approvals-and-sandbox`). If a
  future Codex changes these, adjust `invoke_codex` in the orchestrator. Unlike
  Claude Code, Codex does **not** auto-load the `manifest-*` skills — the
  denylist + CI gates are what enforce the guardrails.
- Auto-merge requires the `autopilot` branch-protection checks to be
  configured; without them, `--auto` merges as soon as GitHub allows.

## PR Merge Train — sweep open PRs into `main`

The Merge Train is Autopilot's **deterministic sibling**. Autopilot acts on
*issues* and never touches `main`; the Merge Train does the opposite — it sweeps
every **open pull request** into `main`. It carries no model and no budget gate
(it spends nothing — pure `git`/`gh`/`npm`/`pytest`), and unlike Autopilot it
**does push to `main`** (each push auto-releases). That is the deliberate,
human-authorized exception to "never touches `main`".

```
 cron (every 6h)
      │
      ▼
┌─────────────────┐   PR_MERGE_TRAIN_ENABLED != true   ┌──────────┐
│ kill switch     │ ─────────────────────────────────► │ no-op    │
└────────┬────────┘                                    └──────────┘
         │ enabled         for each open PR, safest first
         ▼
   git merge PR → main(local)
         │  clean ─────────────────────────┐
         │  conflict = lockfile only ─► regenerate lockfile ─┤
         │  conflict = code/manifest ─► abort + comment + SKIP (human)
         ▼                                  │
   run scripts/check.py-equivalent checks (ruff/pytest/npm ci+test+build)
         │  green ─► keep   │  red ─► reset out of main + comment + SKIP
         ▼
   push main once ─► delete each merged branch (never main/autopilot)
```

**Safety model.** A PR that cannot land *cleanly **and** green* is left exactly
as it was, with an explanatory comment, for a human — `main` never receives a
red or hand-guessed merge. Only regenerable lockfile conflicts
(`**/package-lock.json`) are auto-resolved; `package.json` and source conflicts
are treated as "needs a human". Protected branches (`main`, `autopilot`) are
**never** deleted, even if they somehow appear as a merged head.

**Turn it on.** Repo → Settings → Variables → `PR_MERGE_TRAIN_ENABLED = true`.
Until then, scheduled runs no-op; manual dispatch always runs (default
`dry_run: true`, so you can shadow it safely first).

| Variable | Default | Purpose |
| --- | --- | --- |
| `PR_MERGE_TRAIN_ENABLED` | `false` | Master on/off. Anything but `true` = no-op on cron. |
| `PR_MERGE_TRAIN_PROTECTED` | `main,autopilot` | Branches never deleted (`main` is always added). |
| `PR_MERGE_TRAIN_BASE` | `main` | Branch PRs are merged into. |
| `PR_MERGE_TRAIN_INCLUDE_DRAFTS` | `false` | `true` also attempts draft PRs. |
| `PR_MERGE_TRAIN_RUN_CHECKS` | `true` | `false` skips the local CI gate (not recommended). |

**Run it now / shadow it:** Actions → *PR Merge Train* → *Run workflow*
(`dry_run` ticked plans without writing; untick to act; set `pr` to limit to one
PR). The journal is `docs/autopilot/MERGE_TRAIN_JOURNAL.md` — one line per run.

## Security Autofix — patch vulnerabilities the moment they land

The third autopilot-family loop. It closes **security alerts** with no human in
the loop, so fixes ship even overnight with your laptop closed:

- **npm** manifests — runs `npm audit fix` (non-breaking only) in every
  `package-lock.json` project, patching the transitive CVEs Dependabot can't
  open a clean PR for.
- **pip** manifests — reads the repo's **live Dependabot alerts** and bumps the
  matching `requirements.txt` pin to the first patched version.

Then it runs the deployable-tree gate (`frontend` npm ci + build + test,
`extensions/manifest-dev` compile) and, if green, **pushes to `main`**
(auto-releasing). A red gate aborts the push. It runs on a 3-hourly cron, so
"whenever they come" means "within ~3 hours," day or night.

```
 cron (every 3h)
      │  SECURITY_AUTOFIX_ENABLED != true ─► no-op
      ▼
  npm audit fix (non-breaking) in every package-lock.json project
  + bump requirements.txt pins from live Dependabot alerts
      │ no change ─► clean exit
      ▼
  deployable gate (frontend build+test, extension compile)
      │ red ─► reset, no push   │ green
      ▼
  push to main (or open a PR if SECURITY_AUTOFIX_PUSH=pr)
```

**This complements Dependabot, it doesn't replace it.** Dependabot opens alert
PRs for *direct* deps (the Merge Train then merges them); Security Autofix
patches the *transitive* CVEs and lands everything without waiting for review.

**Turn it on:** repo → Settings → Variables → `SECURITY_AUTOFIX_ENABLED = true`.
Also enable GitHub's **Dependabot security updates** (Settings → Code security)
— that's what makes alerts appear the instant an advisory drops, which this loop
then acts on.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECURITY_AUTOFIX_ENABLED` | `false` | Master on/off (cron no-ops unless `true`). |
| `SECURITY_AUTOFIX_PUSH` | `direct` | `direct` pushes to `main`; `pr` opens a PR instead. |
| `SECURITY_AUTOFIX_BASE` | `main` | Branch fixes land on. |

**Shadow it first:** Actions → *Security Autofix* → Run workflow (`dry_run`
ticked applies fixes locally and prints them without pushing). Journal:
`docs/autopilot/SECURITY_AUTOFIX_JOURNAL.md`.

> Scope note: only **non-breaking** npm fixes are auto-applied. Semver-major
> bumps and vulns with no clean fix (e.g. a transitive needing a library
> migration) are left for a human and reported — `main` never gets a forced or
> guessed security bump.

## Related

- `backend/scripts/run_autopilot_agent.py` — the issue-fixing orchestrator.
- `backend/scripts/run_pr_merge_train.py` — the PR-merge-train orchestrator.
- `backend/scripts/run_security_autofix.py` — the security-autofix orchestrator.
- `.github/workflows/autopilot.yml` / `autopilot-retro.yml` — cron + self-tuning.
- `.github/workflows/pr-merge-train.yml` — the merge-train cron + dispatch.
- `.github/workflows/security-autofix.yml` — the security-autofix cron + dispatch.
- `docs/BUG_FIX_AGENT.md` — the v1 diagnose-only agent this builds on.
- `docs/COST_TRACKING.md` — the cost ledger the budget gate reads.
