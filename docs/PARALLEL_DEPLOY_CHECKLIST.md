# Parallel deploy checklist (Vercel + Render staging)

Use this while **Replit remains production**. All tests run against **Vercel Preview** + **Render staging** + **cloned staging database** — not live Replit users.

## Wiring

| Component | Action |
|-----------|--------|
| Render staging | Deploy from [`render.yaml`](../render.yaml); set secrets per [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md) |
| Staging DB | Clone from Replit per [DATABASE_MIGRATION.md](./DATABASE_MIGRATION.md) |
| Vercel preview | Import repo, root `frontend/`; see [VERCEL_DEPLOYMENT.md](./VERCEL_DEPLOYMENT.md) |
| Backend URL on Vercel | Update `frontend/vercel.json` rewrites **or** set `REACT_APP_GRAPHQL_URL` on Preview |
| CORS on Render | `FRONTEND_ORIGINS=https://YOUR-PROJECT.vercel.app` |
| Email links | `APP_BASE_URL=https://YOUR-PROJECT.vercel.app` on Render |

## Functional tests

### Auth

- [ ] Landing `/` loads
- [ ] Guest session (`startGuestSession`) — workspace loads
- [ ] Email signup
- [ ] Email login
- [ ] Logout
- [ ] Continue with Open Media signs in and returns to `/ideas` (a guest workspace is merged)
- [ ] **Skip** Replit OIDC on Vercel (expected unsupported)

### Core product

- [ ] Create idea
- [ ] Save idea workspace / navigate aspects
- [ ] Generate business model canvas section
- [ ] Generate pitch deck
- [ ] Similar ideas query returns results
- [ ] Publish toggle (if full account)

### UI / assets

- [ ] `/docs` hub and legal pages
- [ ] Static assets under `/assets`
- [ ] Generated PDFs under `/generated` (if applicable)
- [ ] Mobile layout: `?view=ios` or iOS device
- [ ] Dark mode toggle

### API / performance

- [ ] GraphQL p95 acceptable on staging (browser Network tab)
- [ ] `/ping` and `/health` on Render return 200
- [ ] No CORS errors in browser console

## Replit verification (unchanged)

- [ ] Production Replit app still serves users
- [ ] No Replit secrets modified during parallel QA

## Sign-off

When all boxes pass, proceed to [PRODUCTION_READINESS_CHECKLIST.md](./PRODUCTION_READINESS_CHECKLIST.md) before DNS cutover.
