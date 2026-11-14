# DNS cutover and rollback

Plan for moving production traffic from Replit to **Vercel (frontend) + Render (backend)** without a prolonged outage.

## Recommended DNS layout

| Host | Target | Notes |
|------|--------|-------|
| `manifeststartup.com` | Vercel | Frontend SPA |
| `www.manifeststartup.com` | Vercel | Redirect or alias |
| `api.manifeststartup.com` | Render | Backend API (if split-origin) |

If you keep **same-origin** rewrites on Vercel pointing at `api.manifeststartup.com`, only the apex/www records need to move to Vercel initially; update API DNS when Render prod is ready.

## Pre-cutover (T-7 to T-1)

1. Lower DNS TTL to **300 seconds** (5 minutes) on affected records.
2. Deploy Vercel **production** and Render **production** from `main`.
3. Run [PARALLEL_DEPLOY_CHECKLIST.md](./PARALLEL_DEPLOY_CHECKLIST.md) against production URLs (smoke only, no user traffic yet).
4. Migrate database per [DATABASE_MIGRATION.md](./DATABASE_MIGRATION.md).
5. Set production secrets on Render and Vercel; verify `FRONTEND_ORIGINS` and `APP_BASE_URL`.
6. Optional: use a **staging subdomain** (`staging.manifeststartup.com`) for final dress rehearsal.

## Cutover (T-0)

1. Put Replit in **maintenance mode** or accept brief dual-write risk (prefer read-only on Replit during flip).
2. Final Replit `pg_dump` if not already on Supabase prod.
3. Update DNS:
   - Point `manifeststartup.com` / `www` to Vercel
   - Point `api.manifeststartup.com` to Render (if used)
4. Verify:
   - `curl -sS https://manifeststartup.com/`
   - `curl -sS https://api.manifeststartup.com/ping`
   - Login and create idea on production URLs
5. Monitor Render logs and PostHog for 30–60 minutes.

## Rollback scenarios

| Scenario | Action |
|----------|--------|
| Vercel frontend broken | Revert DNS apex/www to Replit; TTL already low |
| Render backend broken | Point `api` DNS back to Replit API host; or revert Vercel rewrites to Replit |
| Bad database migration | Restore Supabase/Postgres from pre-cutover backup; point `DATABASE_URL` to backup instance; keep Replit DB as last resort |
| Partial outage (API only) | Temporary Vercel rewrites to Replit backend URL while fixing Render |

## Rollback drill (before cutover)

1. Document current Replit URLs and DNS records.
2. Deploy staging stack; practice DNS flip on a **test subdomain** only.
3. Time how long rollback takes with 300s TTL.

## Post-cutover

- Keep Replit deployment **running** 1–2 weeks (no traffic).
- After stability, follow [REPLIT_REMOVAL_PLAN.md](./REPLIT_REMOVAL_PLAN.md) (explicit approval required).

## Replit during parallel phase

**No DNS changes** until production readiness sign-off. Replit continues to serve all user traffic.
