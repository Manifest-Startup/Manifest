# Performance baseline & budgets

Phase 1 of the [Performance Migration Strategy](../.cursor/plans/performance_migration_strategy_74c02585.plan.md):
*no optimization without a baseline.* This file is the source of truth for the
performance budgets and how we measure against them. Update the "Measured"
column whenever a phase lands.

## Phase status

| Phase | Status | Notes |
|---|---|---|
| 1 Measurement | ✅ shipped | k6 (`loadtest/`), this doc, size-limit CI gates |
| 2 Async I/O | ✅ shipped (partial) | `AIRouter.achat`, doc-gen resolvers off the loop, multi-worker uvicorn. Remaining: native AsyncOpenAI, port read resolvers to `execute_raw_async` (behind `ASYNC_DB`) |
| 3 Job queue | ✅ shipped (code) | `generation_jobs` + worker + `enqueueBackgroundTasks`/`generationJob`. **Activate:** apply migration, deploy `manifest-generation-worker`, point producers at it |
| 4 Caching | ✅ shipped | `cache_service` (Redis when `REDIS_URL` set, else in-process). Remaining: edge GraphQL cache / persisted queries |
| 5 Front-end | ◑ subset shipped | lazy analytics, font de-block, dead deps. **Full Next.js edge SSR is a separate multi-week effort** |
| 6 Media → object storage | ⬜ not started | needs S3/Supabase Storage |
| 7 DB pooling (PgBouncer) | ⬜ not started | Supabase transaction pooler config |
| 8 Cutover + CI gates | ⬜ not started | staged per phase |

Operator activation flags (all default-safe): `WEB_CONCURRENCY`, `REDIS_URL`,
`ASYNC_DB`. See issue #215 for the runbook.

## SLO budgets (from the strategy, §0)

| Metric | Budget | Enforced by |
|---|---|---|
| Static/cached page paint (LCP) | < 1.0s p75 | Lighthouse CI (`lighthouserc.cjs`) |
| Cached GraphQL reads | < 50ms p95 edge / < 150ms p95 origin | `loadtest/smoke.js` (k6) |
| Uncached GraphQL reads | < 400ms p95 | k6 |
| GraphQL mutations (non-AI) | < 600ms p95 | k6 |
| AI generation | first token < 1.5s, streamed | manual / RUM |
| Boot-critical JS (entry+react+apollo) | < 200 KB gzip | `size-limit` (CI `frontend-performance`) |
| Total shipped JS | < 1.1 MB gzip | `size-limit` |

## Front-end bundle (measured)

Captured from `npm run build && npx size-limit` after the rolldown chunking
fix (2026-07-03):

| Chunk | gzip |
|---|---|
| Boot-critical (`index` + `react-vendor` + `apollo`) | **~174 KB** |
| Total shipped JS (all chunks) | **~992 KB** |

Notable: **posthog-js (~61 KB gzip) is now lazy-loaded** (only after analytics
consent) instead of eager at boot; the Google Fonts request is no longer a
render-blocking CSS `@import`.

**2026-07-03 regression fix:** Vite 8's rolldown `manualChunks` compatibility
shim was recursively capturing group dependencies, which pulled
`react/jsx-runtime` into the `pdf` chunk and `react` into `apollo` — every
page boot-loaded ~230 KB gzip of pdf.js + TipTap (real boot payload ~406 KB
while size-limit still reported 174 KB, because it only sums three named
chunk patterns). Fixed by moving to rolldown's native `codeSplitting` groups
with `includeDependenciesRecursively: false` + `strictExecutionOrder: true`
([frontend/vite.config.ts](../frontend/vite.config.ts)). A new CI guard,
`frontend/scripts/check-boot-chunks.mjs`, fails the build if `pdf`, `editor`,
`pptx`, `hls`, or `analytics` chunks are ever referenced from the built
`index.html` boot path again.

## Voice latency (measured, production, 2026-07-03 — pre-deploy baseline)

Measured against the deployed site through the guest voice flow:

| Step | Measured |
|---|---|
| `POST /api/voice-agent/start` (opening message) | 4.4s |
| `POST /process-stream` time-to-first-delta | 2.1-2.5s |
| `POST /tts` (one short sentence) | 2.5-3.8s |

Streaming itself works end-to-end (incremental SSE deltas confirmed). The
TTS numbers are far above `tts-1`'s typical ~0.5-1s, which points at the
deployment overriding `VOICE_AGENT_TTS_MODEL` to `gpt-4o-mini-tts` — flipping
that env var back to `tts-1` is the single biggest voice win available
(~2-3s per spoken sentence). Code-side fixes shipped alongside this note:
voice endpoints moved off the event loop (threadpool handlers), and the
per-turn context load is cached (`VOICE_CONTEXT_CACHE_TTL_SECONDS`).
Re-measure after deploy and update this table.

## How to measure

```bash
# Front-end bundle budgets (also runs in CI: frontend-performance job)
cd frontend && npm run build && npx size-limit

# Lighthouse (lab) on a production build
cd frontend && npx lhci autorun

# Load test against a STAGING deploy (never prod)
BASE_URL=https://staging.manifeststartup.com \
GRAPHQL_URL=https://staging-api.manifeststartup.com/graphql \
k6 run loadtest/smoke.js
```

## Re-run cadence

Re-run `size-limit` + Lighthouse on every PR (already CI-gated) and the k6
script after each backend phase (async I/O, queue, cache) against staging.
Record the new numbers here so regressions are visible as a diff.
