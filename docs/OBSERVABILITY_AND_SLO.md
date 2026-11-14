# Observability and SLOs

Last updated **May 23, 2026** — Stage #1 of the backend migration ([issue #215](https://github.com/Manifest-Startup/Manifest/issues/215)) added request-ID propagation, JSON logs, `/metrics`, and extended per-request DB query metrics from `/graphql` to **all** routes.

This document aligns on-call and product engineering around **service level objectives (SLOs)** and where to pull the supporting metrics in Manifest’s stack (FastAPI, GraphQL, Postgres, LLM calls, PostHog).

## Request correlation — `X-Request-Id`

**Signals**

- Every HTTP response carries an `X-Request-Id` header (`backend/app/middleware/request_id.py`).
  - If the request arrived with an upstream `X-Request-Id` (e.g. from Cloudflare, a chained service, or a browser dev tool), it is honored verbatim (clamped at 128 chars).
  - Otherwise a fresh 32-char hex UUID4 is generated.
- The ID is bound to a `ContextVar` (`get_request_id()`) so the JSON logger threads it into **every** log line without explicit plumbing — search a single ID in your aggregator to reconstruct the entire request, including the 6–11 LLM calls and DB queries it fans out to.
- The header is appended on every response, including errors, so a user reporting a bug can quote it.

**Use it**

- Filter logs by `request_id="..."` to follow a single GraphQL mutation across resolvers, services, and slow-query log lines.
- Quote `X-Request-Id` in production-test/Sentry/PostHog bug reports so support engineers don’t have to grep by timestamp.

## Structured JSON logs

**Signals**

- `backend/app/utils/logger.py` emits one JSON line per record when `LOG_FORMAT=json` (recommended default in Render / production).
- Each line contains: `ts` (UTC ISO-8601 with millis), `level`, `logger`, `msg`, `file`, `line`, `request_id` (when inside a request), plus every `extra=` field passed by the caller (e.g. `duration_ms`, `slow_queries`).
- Set `LOG_FORMAT=text` for the legacy human-readable format (default in local dev).
- Set `LOG_LEVEL=INFO|WARNING|ERROR|DEBUG` to control verbosity.

## /metrics — Prometheus text exposition

**Signals**

- `GET /metrics` returns Prometheus text exposition format for any external scraper (Grafana Cloud, Datadog, OpenObserve, self-hosted Prometheus). Wired by `setup_metrics(app)` in `backend/app/main.py` via [`prometheus-fastapi-instrumentator`](https://github.com/trallnag/prometheus-fastapi-instrumentator).
- Default metrics: `manifest_http_requests_total{method, status, handler}`, `manifest_http_request_duration_seconds{...}` (histogram), `manifest_http_inprogress{...}`.
- `/ping`, `/metrics`, `/health`, `/healthz` are excluded so the scraper does not measure itself.
- **Toggle:** set `METRICS_ENABLED=false` to skip wiring (e.g. on a worker that already exposes metrics differently).

**Defense in depth**

- The endpoint is intentionally unauthenticated so a Prometheus scraper needs no credential. Network-level protection is primary:
  - On Render — host the API as a **private** service and scrape from a sibling Grafana Agent.
  - On Vercel rewrites / Cloudflare — block `/metrics` for public traffic at the edge.
- If the new dep is missing in an environment (offline CI, hot-reload after a clean), `setup_metrics(app)` logs a warning and `/metrics` returns 404 — the rest of the app stays up.

## GraphQL latency

**Signals**

- Response headers on every non-health response (see `performance_metrics_middleware` in `backend/app/main.py`):
  - `X-Manifest-Duration-Ms` — wall time of the HTTP request (NEW in Stage #1, emitted on **every** instrumented route).
  - `X-Manifest-GraphQL-Duration-Ms` — backward-compatible alias, still emitted on `/graphql` for any existing consumer.
  - `X-Manifest-DB-Query-Count` — number of DB round-trips recorded for the request.
  - `X-Manifest-DB-Connection-Count` — connections opened from the app’s perspective during the request (per-query metrics context).
  - `X-Request-Id` — see “Request correlation” above.
- Structured logs when duration exceeds `SLOW_REQUEST_MS` (falls back to `GRAPHQL_SLOW_REQUEST_MS`, default **750** ms): `[performance] slow GraphQL request` (or `slow request` for REST) with `duration_ms`, `query_count`, `slow_queries`, `method`, `path`, `request_id`, etc.

**Suggested SLO (starting point)**

| Tier | p95 `X-Manifest-GraphQL-Duration-Ms` | Error rate |
|------|--------------------------------------|-------------|
| Interactive reads (e.g. `me`, `ideas`, `idea`) | &lt; 800 ms | &lt; 0.5% |
| Mutations that only persist state | &lt; 1200 ms | &lt; 1% |

Tune per environment; document changes in runbooks when tightening.

**Dashboards**

- APM or log aggregation: histogram on `duration_ms` from slow-request logs; filter by `path`.
- Optional: forward selected slow events to PostHog as server-side captures (keep cardinality low; avoid logging full queries with PII).

## Database pool

**Signals**

- Internal JSON: `GET /api/internal/ops/snapshot` (see [docs/API.md](API.md)) returns `db_pool`:
  - `pooled_connections_checked_out` — active checkouts from the psycopg2 pool (incremented in `get_db_connection` when pooling is used).
  - `min_connections` / `max_connections` — from `DB_POOL_MIN_CONNECTIONS` / `DB_POOL_MAX_CONNECTIONS`.
  - `pool_initialized`, `pooling_enabled`, `postgresql_configured`.

**Suggested SLO**

- Steady-state: `pooled_connections_checked_out` &lt; `max_connections` with headroom (e.g. sustained &lt; 70% of max).
- Alert if checkout count approaches max for several minutes **or** DB latency spikes correlate with pool exhaustion.

## Async database pool (Stage #2)

**Signals**

- Same ops snapshot (`GET /api/internal/ops/snapshot`) returns `async_db_pool` when the Stage #2 module is present:
  - `async_db_enabled` — whether `ASYNC_DB=true` was set at boot.
  - `pool_open` — whether the `psycopg` 3.x `AsyncConnectionPool` finished opening.
  - `driver_available` — whether `psycopg[binary,pool]` is installed.
  - `connections_in_pool` / `connections_available` / `requests_waiting` — from pool stats when open.
- `GET /ping` includes an `async_db` object when `ASYNC_DB=true`: `{ enabled, pool_open, ping_ok }` after a live `SELECT 1`.

**Toggle**

- Default off. Set `ASYNC_DB=true` only after `DATABASE_URL` points at real Postgres. Sync `psycopg2` queries continue unchanged until individual resolvers migrate to `execute_raw_async` / future `execute_async` helpers in later stages.

**Suggested SLO (once enabled in production)**

- `ping_ok: true` on `/ping` from every region/worker.
- `requests_waiting` sustained at 0; alert if &gt; 0 for several minutes (pool exhaustion under async load).

## DB query work per request

**Signals**

- Same slow GraphQL log line includes `total_query_ms` and `slow_queries` (per statement over `DB_SLOW_QUERY_THRESHOLD_MS`, default **100** ms).

**Suggested SLO**

- p95 `query_count` for hot operations (document in runbooks per operation once profiled).
- Investigate N+1 patterns when `query_count` grows with list size.

## LLM cost and latency

**Signals**

- Application logs from `AILayer` / `AIRouter` paths (search for model and timing patterns in `backend/app/services/`).
- PostHog LLM analytics (see `AGENTS.md` and PostHog instrumentation skills) for token and cost attribution when enabled.

**Suggested SLO**

- Cap p95 latency for voice and interactive flows separately from batch document generation.
- Budget alerts on daily token spend by environment.

## Background job queue depth

**Current state**

- Document and artifact generation still uses **in-process threads**; there is **no** shared queue depth metric yet.
- `GET /api/internal/ops/snapshot` returns `background_job_queue.status: "not_implemented"` until a queue exists ([docs/ASYNC_JOB_QUEUE_DESIGN.md](ASYNC_JOB_QUEUE_DESIGN.md)).

**Target signal (after queue implementation)**

- Depth, age of oldest job, failed/retry counts, worker concurrency — chart in the primary metrics stack.

## Related docs

- [docs/API.md](API.md) — `GET /api/internal/ops/snapshot` auth header.
- [docs/ARCHITECTURE_REFERENCE.md](ARCHITECTURE_REFERENCE.md) — runtime topology.
- [docs/ASYNC_JOB_QUEUE_DESIGN.md](ASYNC_JOB_QUEUE_DESIGN.md) — planned async work model.
