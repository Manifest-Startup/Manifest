# Production Smoke Testing → GitHub Issue Auto-Filing

Continuous Playwright smoke tests run on a cron against the deployed
Manifest site. Each test execution posts its result to an internal
backend endpoint which persists the row, dedupes against open GitHub
issues, and (on failure) files a new issue via the existing
`GitHubIssueService`. This is Phase 2b of the agentic-automation
roadmap.

## What's in

- `production_test_runs` table — one row per test execution with
  status, error details, captured artifacts, suspected files, CI
  traceability, and the linked GitHub issue (created or deduped).
  Migration:
  [`20260522150000_production_test_runs.sql`](../supabase/migrations/20260522150000_production_test_runs.sql).
- `production_test_service` — record, dispatch, dedupe, stats.
  Plugs into the existing
  [`GitHubIssueService`](../backend/app/services/integrations/github_issues.py)
  so failure-issue creation uses the same dedupe rules as the website-
  audit and survey-feedback loops.
- Internal REST surface at `/api/internal/production-tests`:
  - `POST /results` — ingest one test execution
  - `GET /recent` — recent runs for ops
  - `GET /stats` — rolling pass/fail roll-up
  - Authenticated via `X-Manifest-Agent-Key`.
- Playwright suite at `tests/production/` with:
  - `playwright.config.ts` — chromium-only baseline, retries=1 in CI,
    traces + screenshots + videos on failure, custom reporter wired in
    automatically.
  - `reporter/manifest-reporter.ts` — converts each `TestCase` →
    `TestResult` into the JSON body the backend expects and POSTs it.
    If the auth secret is missing, the reporter logs locally instead
    of posting — safe for `playwright test` invocations during local
    development.
  - Two canonical smoke tests (`landing.spec.ts`,
    `guest-session.spec.ts`). Both tagged `@sev:high` so failure
    issues come back labeled `severity:high`.
- GitHub Actions workflow
  [`.github/workflows/production-tests.yml`](../.github/workflows/production-tests.yml):
  scheduled every 6 hours, on every PR touching the app, and via
  `workflow_dispatch`.

## How issue dedupe works

Each failure builds a stable title key:

```
[prod-test] <test_name> — <first line of error_message, ≤100 chars>
```

`GitHubIssueService.create_issues` normalizes the title (lowercase,
alphanumerics only, single-spaced) and skips creation if any open
issue in the repo has the same normalized title. The
`production_test_service` then asks GitHub for the matching open
issue's URL and records it on the test_run row as
`linked_existing_issue_url`. So:

- First failure of a given mode → new issue created.
- Subsequent identical failures → no duplicate issue.
- Different failure mode on the same test → different first-error
  line → new issue.

## Severity labels

Every failure issue gets `bug`, `automated-test`, `production`, plus
one of `severity:high|medium|low`. Override by tagging the Playwright
test:

```ts
test.describe("landing @sev:high", () => { ... });
```

## Local development

```bash
cd production-tests
npm install
npx playwright install --with-deps chromium

# Point at your local dev server. The reporter falls back to local-
# log mode when MANIFEST_AGENT_LOOP_SECRET is unset.
export MANIFEST_TEST_TARGET_URL=http://localhost:5000
npx playwright test
```

## CI configuration

| Name | Where | Why |
|---|---|---|
| `MANIFEST_AGENT_LOOP_SECRET` | secret | Authenticates the reporter against `/api/internal/production-tests/results`. |
| `MANIFEST_GITHUB_TOKEN` (or `GITHUB_TOKEN`) | secret | Used by the backend's `GitHubIssueService` to create/dedupe issues. |
| `MANIFEST_GITHUB_REPO` | env on the deployed backend | e.g. `acme/manifest`. The backend won't file issues without it. |
| `MANIFEST_TEST_TARGET_URL` | repo var (optional) | Defaults to `https://manifeststartup.com`. |
| `MANIFEST_INTERNAL_API_URL` | repo var (optional) | Defaults to the target URL. |

## Read APIs for ops

```bash
curl -H "X-Manifest-Agent-Key: $SECRET" \
  https://your-backend/api/internal/production-tests/stats?hours=24

curl -H "X-Manifest-Agent-Key: $SECRET" \
  https://your-backend/api/internal/production-tests/recent?status=fail&limit=20
```

The same payloads power the admin dashboard at `/admin/cost`.

## Tests

[`backend/tests/test_production_test_service.py`](../backend/tests/test_production_test_service.py)
covers: persistence, validation, issue title + body shaping, no-op
on pass, no-repo skip, fresh-issue creation with linkage written
back, dedupe → existing-issue URL recorded, graceful skip when
GitHub token missing, status filtering on the recent endpoint, and
the stats roll-up.
