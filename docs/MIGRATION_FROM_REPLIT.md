# Migration from Replit

> **Superseded (2026-11):** the live migration path is [CLOUDFLARE_MIGRATION.md](./CLOUDFLARE_MIGRATION.md) (Cloudflare edge Worker + Render free backend + Supabase). This document is kept as history.

Safe, parallel migration from Replit to **GitHub + Vercel (frontend) + Render (backend)** while Replit stays live until verification is complete.

**Principles**

- Do not break the existing Replit deployment.
- Do not delete Replit-specific code or configs until [REPLIT_REMOVAL_PLAN.md](./REPLIT_REMOVAL_PLAN.md) is explicitly approved.
- Ship incrementally via branches and pull requests.
- Production data today lives on **Replit Postgres**; Supabase migrations in `supabase/migrations/` are the long-term target.

## Target architecture

| Phase | Frontend | Backend | Database | Traffic |
|-------|----------|---------|----------|---------|
| **Now (parallel)** | Replit (prod) | Replit (prod) | Replit Postgres | Users |
| **Staging** | Vercel preview | Render staging | Cloned staging Postgres | Team / QA |
| **Cutover** | Vercel production | Render production | Supabase Postgres (migrated) | Users |
| **Retire** | — | — | Replit DB backup only | — |

See also: [VERCEL_DEPLOYMENT.md](./VERCEL_DEPLOYMENT.md), [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md), [DATABASE_MIGRATION.md](./DATABASE_MIGRATION.md), [PARALLEL_DEPLOY_CHECKLIST.md](./PARALLEL_DEPLOY_CHECKLIST.md), [PRODUCTION_READINESS_CHECKLIST.md](./PRODUCTION_READINESS_CHECKLIST.md), [DNS_CUTOVER_AND_ROLLBACK.md](./DNS_CUTOVER_AND_ROLLBACK.md), [PERFORMANCE_MIGRATION_NOTES.md](./PERFORMANCE_MIGRATION_NOTES.md), [REPLIT_REMOVAL_PLAN.md](./REPLIT_REMOVAL_PLAN.md).

## Repository map

| Layer | Path | Notes |
|-------|------|-------|
| Frontend | `frontend/` | Vite 7, React 19; build output **`build/`** |
| Backend | `backend/` | FastAPI + GraphQL; Docker image in `backend/Dockerfile` |
| Migrations | `supabase/migrations/` | Apply to Supabase when cutting over from Replit Postgres |
| Local dev | `manifest-dev setup` / `manifest-dev start` | See [LOCAL_DEV_WITHOUT_REPLIT.md](./LOCAL_DEV_WITHOUT_REPLIT.md) |

## Replit-specific code (keep until Phase 9)

| Area | Location |
|------|----------|
| Replit OIDC | `backend/app/auth/replit_auth.py`, `backend/app/routes/auth_routes.py` |
| Replit CORS | `backend/app/main.py` (`REPLIT_DEV_DOMAIN`, `REPLIT_DOMAINS`) |
| Replit doc | `replit.md` |

**Auth on the new stack:** **Continue with Open Media** (`/api/auth/open-media/start`, ADR 0002) and **guest sessions**. Email/password GraphQL and Replit OIDC were removed.

## PR roadmap

| PR | Branch | Scope |
|----|--------|-------|
| 1 | `chore/migration-docs` | Docs, `.env.example`, build/dist drift fixes |
| 2 | `feat/vercel-frontend` | `frontend/vercel.json`, Vite env defines |
| 3 | `feat/render-backend` | `render.yaml`, `/health`, `FRONTEND_ORIGINS` |
| 4 | `chore/migration-env-db` | DB clone + Supabase migration runbook |
| 5 | `feat/parallel-deploy` | Wire Vercel preview → Render staging; QA checklist |
| 6+ | `perf/*` | Incremental performance (lazy routes, polling) |
| 8 | `docs/cutover` | DNS + production readiness (before traffic flip) |
| 9 | `chore/replit-removal-*` | **Blocked** until explicit approval — see [REPLIT_REMOVAL_PLAN.md](./REPLIT_REMOVAL_PLAN.md) |

## Environment variables

Full catalog: [`.env.example`](../.env.example) at repo root. Deploy-focused summary:

### Render backend (required)

- `DATABASE_URL` — Postgres (staging clone, then Supabase prod)
- `SESSION_SECRET` — long random string
- `ENVIRONMENT` — `staging` or `production`
- `OPENAI_API_KEY`, `AI_MODEL`
- `UVICORN_FORWARDED_ALLOW_IPS` — Render load balancer CIDRs
- `FRONTEND_ORIGINS` — comma-separated Vercel preview/prod URLs
- `APP_BASE_URL` — public frontend URL

### Vercel frontend (build-time)

- `REACT_APP_PUBLIC_POSTHOG_KEY`, `REACT_APP_PUBLIC_POSTHOG_HOST`
- `REACT_APP_GRAPHQL_URL` — optional; omit when using `vercel.json` rewrites
- `REACT_APP_VERSION` — release tag or git SHA

### Replit only (unset on Render/Vercel)

- `REPL_ID`, `ISSUER_URL`, `REPLIT_DEV_DOMAIN`, `REPLIT_DOMAINS`

## Branch strategy

- Feature branches → PR → `main`
- CI: `.github/workflows/main.yml` (pytest, Jest, Cypress)
- Releases: auto SemVer on push to `main` (Conventional Commits)
