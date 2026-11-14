# Internal Website Issue Sync

Last verified against code on **May 1, 2026**.

This workflow powers Manifest's internal agent feedback loop. Agents can audit public pages such as `https://manifeststartup.com`, turn the findings into GitHub-ready issue candidates, and optionally create those issues directly in the repository.

## Source Files

- `backend/app/services/operations/website_issue_sync.py`
- `backend/app/routes/website_testing_routes.py`
- `backend/scripts/run_website_issue_sync.py`
- `mcp_server/src/manifest_mcp/client.py`
- `mcp_server/src/manifest_mcp/server.py`
- `.github/workflows/website-testing.yml`

## How It Works

1. Discover public same-origin pages from `sitemap.xml` and homepage links.
2. Crawl a bounded number of public routes, skipping `/api/*` and `/graphql`.
3. Extract page signals such as status codes, metadata, headings, shell content, and internal links.
4. Generate issue candidates from deterministic heuristics and, when available, AI summarization through `AIRouter`.
5. De-duplicate against open GitHub issues by normalized title.
6. Ensure required labels exist, then create GitHub issues directly.

This is operational tooling for improving Manifest itself, not a customer-facing product surface.

## Backend API

Base path: `/api/internal/website-testing`

Endpoint:

- `POST /api/internal/website-testing/sync-issues`

Auth:

- `X-Manifest-Agent-Key: <MANIFEST_AGENT_LOOP_SECRET>`

Request body:

```json
{
  "target_url": "https://manifeststartup.com",
  "max_pages": 6,
  "max_issues": 6,
  "create_github_issues": true,
  "dry_run": false,
  "github_repo": "Manifest-Startup/Manifest",
  "extra_labels": ["triage"]
}
```

## CLI Script

Manual run:

```bash
PYTHONPATH=backend python backend/scripts/run_website_issue_sync.py \
  --target-url https://manifeststartup.com \
  --max-pages 6 \
  --max-issues 6
```

Dry run:

```bash
PYTHONPATH=backend python backend/scripts/run_website_issue_sync.py \
  --target-url https://manifeststartup.com \
  --dry-run
```

## MCP Tool

Tool name:

- `audit_website_and_create_github_issues`

Recommended MCP env:

```bash
export MANIFEST_API_URL="http://localhost:8000"
export MANIFEST_API_TOKEN="jwt-for-graphql-tools"
export MANIFEST_AGENT_LOOP_SECRET="shared-internal-secret"
```

`MANIFEST_AGENT_LOOP_SECRET` is used for the internal website issue sync REST endpoint.

## GitHub Workflow

Workflow file:

- `.github/workflows/website-testing.yml`

Triggers:

- nightly schedule
- manual dispatch

The workflow installs backend dependencies, runs the shared CLI script, and uploads the JSON audit result as an artifact.

## Required Environment Variables

Backend/service:

- `MANIFEST_AGENT_LOOP_SECRET` or `AGENT_LOOP_SECRET` for the internal REST entrypoint
- `MANIFEST_GITHUB_TOKEN` or `GITHUB_TOKEN`
- `MANIFEST_GITHUB_REPO` or `GITHUB_REPOSITORY`

Optional:

- `OPENAI_API_KEY`
- `WEBSITE_ISSUE_SYNC_MODEL`

Without `OPENAI_API_KEY`, the service still works using deterministic heuristics only.
