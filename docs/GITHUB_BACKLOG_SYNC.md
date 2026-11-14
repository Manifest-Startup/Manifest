# GitHub backlog sync (Manifest-Startup/Manifest)

Last synced: **2026-05-17**.

## Repository and access

- Remote: `https://github.com/Manifest-Startup/Manifest.git`
- Org project: `@Manifest-Startup / Manifest` (Projects v2)
- Local CLI: `gh auth status` (scopes: `repo`, `workflow`, `project`, `read:org`)

## Open issues (product / UX)

| # | Stream | Action |
|---|--------|--------|
| 75–78 | Website audit — headings | Fixed via route-specific SPA shells (`web/spa_prerender_shell.py`, `spa-shell-bootstrap.js`). Close after deploy + audit re-run. |
| 79 | SEO — duplicate pre-hydration shell | Shells differ per route (`/`, `/login`, `/signup`, `/pitch-reels`, …). |
| 80 | No-JS / crawler resilience | Richer `<noscript>` + static `<main>` in index HTML. |

## Open issues (security ops)

| # | Stream | Action |
|---|--------|--------|
| 170 | Advisory scanner paging | Triage: `urllib3` bump, HIBP `usedforsecurity=False`, bandit baseline, semgrep exclude for logger false positives. Re-run `security.yml`; auto-close when `steps.failed.outputs.any == false`. |

## Implementation streams (prioritize-stream)

| Stream | Canonical docs | Code entrypoints |
|--------|----------------|------------------|
| Product UX | [PRODUCT_VISION.md](PRODUCT_VISION.md), [API.md](API.md) caveats | `frontend/src/App.tsx`, `frontend/public/index.html` |
| Security SEC-### | [security/FINDINGS_BACKLOG.md](security/FINDINGS_BACKLOG.md) | `.github/workflows/security.yml`, `backend/app/security/` |
| Infra — media | [MEDIA_OBJECT_STORAGE_MIGRATION.md](MEDIA_OBJECT_STORAGE_MIGRATION.md) | `pitch_reels/video_worker.py`, `pitch_reels/service.py` |
| Infra — jobs | [ASYNC_JOB_QUEUE_DESIGN.md](ASYNC_JOB_QUEUE_DESIGN.md) | `runBackgroundTasks`, `idea_utils.py` |

## Useful commands

```bash
gh issue list --repo Manifest-Startup/Manifest --state open
gh run list --repo Manifest-Startup/Manifest --workflow "Security – SAST / SCA / SBOM / Secrets" --limit 3
PYTHONPATH=backend python backend/scripts/run_website_issue_sync.py --target-url https://manifeststartup.com --dry-run
```
