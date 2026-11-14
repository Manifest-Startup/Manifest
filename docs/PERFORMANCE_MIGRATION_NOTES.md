# Performance notes (post-parallel deploy)

Incremental improvements after Vercel + Render staging is green. Do not rewrite the app.

See [saved-ideas loading verification](PERFORMANCE_IDEAS_LOADING.md) for the September 2026 session, query, and bundle fixes.

## Already in place

- Route-level **lazy loading** in [`frontend/src/App.tsx`](../frontend/src/App.tsx) (marketing, ideas, docs, auth, messaging)
- Vite **manual chunks** for Apollo, React, editor, PDF, PostHog ([`frontend/vite.config.ts`](../frontend/vite.config.ts))
- CI **size-limit** and Lighthouse on production build (`.github/workflows/main.yml`)
- Backend **slow request logging** and optional `ASYNC_DB` pool

## Recommended next PRs (one concern each)

| Priority | Change | Rationale |
|----------|--------|-----------|
| Medium | Enable `ASYNC_DB=true` on Render after pool metrics review | Reduces blocking sync DB in hot paths |
| Medium | Messaging: replace 15–30s Apollo `pollInterval` with Socket.IO when frontend stub is enabled | Less idle traffic |
| Low | `AI_INTERACTIVE_CACHE_TTL_SECONDS` tuning for repeat prompts | Cuts OpenAI cost/latency |
| Low | CDN for `/generated` PDFs via Supabase Storage public URLs | Offload backend disk |
| Low | Remove committed `frontend/dist/` artifacts from git history (already gitignored) | Repo hygiene |

## Polling inventory (messaging / nav)

| Component | Interval |
|-----------|----------|
| `ChatPanel` | 15s |
| `ConversationsList`, `MessagesPage`, `CollaborationInvitations` | 30s |
| `NavigationBar`, `IOSNavigationBar` | 120s |
| `BillingDashboardPage` | 30s |
| `AdminCostDashboardPage` | 60s |

Before reducing intervals, confirm Socket.IO is wired end-to-end (`frontend/src/features/core/socket.ts` is currently a no-op stub).

Since 2026-07-03 all polling queries skip their tick while the tab is hidden
(`skipPollAttempt` in the Apollo client defaults —
[`frontend/src/features/core/apollo/client.ts`](../frontend/src/features/core/apollo/client.ts)),
so background tabs no longer generate this traffic at all.

## AI latency

Dominant user-perceived latency is **OpenAI generation** (pitch deck, BMC, similar ideas). Mitigations already available:

- Model selection via `AI_MODEL` / feature-specific env vars
- Optional `PITCH_DECK_WEB_RESEARCH=0` (default off) to skip extra web calls
- Pitch-reel cost guardrails in `.claude/skills/manifest-pitch-reel-cost-guard/`

## Bundle analysis

```bash
cd frontend && npm run build
npx vite-bundle-visualizer  # if added as devDep; or inspect build/assets in CI size-limit
```

See CI job `frontend-performance` in `.github/workflows/main.yml`.
