# Production signals ops

Last verified against code on **May 1, 2026**.

## Purpose

Ingest **deduped** production anomaly signals and optionally open **GitHub issues** when a fingerprint crosses a threshold inside a rolling time window. This is **not** one issue per user click.

## API

- `POST /api/internal/production-signals/event`
- Header: `X-Manifest-Agent-Key: <MANIFEST_AGENT_LOOP_SECRET>`

JSON body:

- `event_name` (required)
- `route` (optional)
- `severity`: `info` | `warn` | `error` | `critical` (`info` is accepted but **not** counted toward thresholds)
- `error_code`, `session_id`, `sample` (optional; samples are redacted server-side)
- `create_github_issue` (bool, default false): when true and thresholds met, create an issue

## Storage

- Table: `production_signal_state` (see `supabase/migrations/20260405143000_production_signal_state.sql`)
- Apply migration in production before enabling traffic.

## Environment

| Variable | Purpose |
|----------|---------|
| `MANIFEST_AGENT_LOOP_SECRET` | Auth for the internal route |
| `PRODUCTION_SIGNAL_WINDOW_SECONDS` | Rolling bucket size (default `900`) |
| `PRODUCTION_SIGNAL_THRESHOLD` | Events per bucket before GitHub eligibility (default `5`) |
| `MANIFEST_GITHUB_TOKEN` / `GITHUB_TOKEN` | Issue creation |
| `MANIFEST_GITHUB_REPO` / `GITHUB_REPOSITORY` | Target repo |

## GitHub Projects v2 (optional)

When `MANIFEST_GITHUB_PROJECT_NODE_ID` is set, **all** issues created through `GitHubIssueService.create_issues` (website audit, survey sync, production signals) attempt a best-effort add to the project and optional Start/End dates:

- `MANIFEST_GITHUB_PROJECT_NODE_ID` — Project v2 node id (`PVT_kw…`)
- `MANIFEST_GITHUB_PROJECT_START_FIELD_ID` — Date field node id
- `MANIFEST_GITHUB_PROJECT_END_FIELD_ID` — Date field node id
- `MANIFEST_GITHUB_PROJECT_ROADMAP_DAYS` — End date offset from start (default `7`)

Fine-grained PAT or GitHub App needs **Issues** and **Projects** write scopes for the target org/repo.

## Allowlist

`error` events open issues when `event_name` is in the backend allowlist (see `ISSUE_EVENT_ALLOWLIST` in `operations/production_signals.py`) **or** when `severity` is `critical`.

## MCP

Tool: `emit_production_signal` (requires `MANIFEST_AGENT_LOOP_SECRET` on the MCP client).
