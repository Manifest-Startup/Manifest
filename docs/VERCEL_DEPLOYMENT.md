# Vercel deployment (Manifest frontend)

Deploy the React/Vite SPA from the `frontend/` directory. Replit production stays untouched until [PRODUCTION_READINESS_CHECKLIST.md](./PRODUCTION_READINESS_CHECKLIST.md) is complete.

## Project settings

| Setting | Value |
|---------|-------|
| Root Directory | `frontend` |
| Framework | Vite |
| Build Command | `npm run sync:docs && npm run build` (also in `vercel.json`) |
| Output Directory | **`build`** |
| Node.js | 20 |

## Connect repository

1. Import the GitHub repo in [Vercel Dashboard](https://vercel.com/new).
2. Set **Root Directory** to `frontend`.
3. Deploy a **Preview** branch first (not production domain).

## Backend routing (two options)

### Option A — Same-origin rewrites (default)

[`frontend/vercel.json`](../frontend/vercel.json) proxies API paths to the backend. By default destinations point at `https://api.manifeststartup.com`.

**Staging / parallel QA:** edit rewrite destinations in `vercel.json` on a branch to your Render staging URL, e.g. `https://manifest-backend-staging.onrender.com`, or override rewrites in the Vercel project **Settings → Redirects/Rewrites** for Preview only.

### Option B — Absolute GraphQL URL (cross-origin)

Set build-time env vars in Vercel:

```env
REACT_APP_GRAPHQL_URL=https://your-backend.onrender.com/graphql
```

The app calls the backend directly. You must add the Vercel preview URL to backend `FRONTEND_ORIGINS` (see [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md)).

## Environment variables (Vercel → Environment Variables)

| Variable | Preview | Production |
|----------|---------|------------|
| `REACT_APP_PUBLIC_POSTHOG_KEY` | staging or prod key | prod key |
| `REACT_APP_PUBLIC_POSTHOG_HOST` | PostHog host | prod host |
| `REACT_APP_GRAPHQL_URL` | optional (Option B) | optional |
| `REACT_APP_VERSION` | git SHA or tag | release semver |

Variables are injected at **build time** via `frontend/vite.config.ts` `define` block.

## Build verification (local)

```bash
cd frontend
npm ci
npm run sync:docs && npm run build
npx serve -s build -l 3000
```

With backend on `:8000`, dev uses Vite proxy (`vite.config.ts`). Production build on Vercel uses rewrites or `REACT_APP_GRAPHQL_URL`.

## OAuth note

Replit OIDC (`/auth/login` on Replit) does **not** apply on Vercel. Use **email/password** and **guest** GraphQL flows for staging tests.

## Manual test checklist (preview)

- [ ] `/` loads; mobile layout (`?view=ios`)
- [ ] Guest session works
- [ ] Signup / login / logout (email)
- [ ] `/docs` hub
- [ ] Network tab: `/graphql` returns 200

Full parallel QA: [PARALLEL_DEPLOY_CHECKLIST.md](./PARALLEL_DEPLOY_CHECKLIST.md).

## Replit compatibility

No changes to Replit secrets or deployment. Vercel is an additional hosting path only.
