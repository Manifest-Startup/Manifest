# Production readiness checklist

Complete before moving production traffic from Replit to the Cloudflare edge stack. Replit remains the rollback environment through the observation window; retirement has a separate approval gate in [REPLIT_REMOVAL_PLAN.md](./REPLIT_REMOVAL_PLAN.md).

## Source and deploy

- [ ] Migration branch changes are merged into GitHub `main`; CI is green on the exact deployed commit.
- [ ] Cloudflare Worker `manifest-production` is deployed from `deploy/cloudflare/wrangler.jsonc` and serves the site at `manifeststartup.com` and `www.manifeststartup.com`.
- [ ] Worker routes GraphQL, REST, auth, Socket.IO, health, generated-file and agent-discovery paths to the configured backend; SPA deep links load from edge assets.
- [ ] The Render backend service created by the Manifest Blueprint is deployed from `main`; `/ping`, `/health`, and `/healthz` return 200.
- [ ] `EDGE_SHARED_SECRET` matches between Worker and Render; direct-origin protected requests are rejected and Worker-routed requests succeed.
- [ ] Render production secrets are set, including `DATABASE_URL`, `SESSION_SECRET`, `OPENAI_API_KEY`, Supabase credentials, and every historical `MANIFEST_KEK_V<n>` needed to decrypt stored data.
- [ ] `FRONTEND_ORIGINS`, `APP_BASE_URL`, `BACKEND_ORIGIN`, and `FILES_PUBLIC_BASE` match the production domains and Supabase project.
- [ ] `/metrics` is scraped or blocked at the edge per [OBSERVABILITY_AND_SLO.md](./OBSERVABILITY_AND_SLO.md); production logs are visible and structured.

## Data and durable files

- [ ] Honor the owner's decision not to import Replit Postgres rows. Confirm the owner understands that Replit accounts, workspaces, and ideas absent from the existing Supabase project will not exist after cutover; keep the Replit database and files intact for rollback.
- [ ] Take a Supabase backup before deployment and confirm that the existing Supabase dataset is the intended starting dataset for the new backend.
- [ ] All repository Supabase migrations are applied and the deployed schema matches the expected application schema.
- [ ] Apply and verify [`20261114090000_lock_down_public_role_grants.sql`](../supabase/migrations/20261114090000_lock_down_public_role_grants.sql) in a staging database before production. The 2026-11-14 production review found blanket anon/authenticated grants on public tables/sequences/functions and unsafe defaults for `postgres` and `supabase_admin`; 13 tables lack RLS and 20 RLS-enabled tables lack policies. This app uses direct Postgres for relational data and has no frontend Supabase table client, so public API-role access should remain revoked unless a documented feature requires it. Add scoped policies and grants only for such features, then verify signup/Auth triggers, backend DB reads/writes, storage uploads, and production jobs before applying to production. Do not enable RLS blindly.
- [ ] Replit Postgres and generated files remain available for rollback; no source data is deleted as part of this migration.
- [ ] Decide whether any Replit-generated files need a separate copy; keep them on Replit until this is resolved. Files already present in Supabase Storage remain readable through the Worker after a Render restart/recreation.

## Production route verification

- [ ] Email signup/login/logout, session refresh, password reset, guest session and guest merge work.
- [ ] Idea CRUD, document generation, pitch deck, BMC, similar ideas and messaging work.
- [ ] REST, GraphQL, Socket.IO live updates, email delivery, OAuth/SSO callbacks, AI generation and background work pass on the public Cloudflare route.
- [ ] Generated PDF download and profile image upload/read work through the public route.
- [ ] Error tracking/analytics receive events; Cloudflare and Render logs/costs remain stable through the agreed observation window (at least seven days).

## DNS, rollback, and sign-off

- [ ] Apex and `www` resolve to the Cloudflare Worker; TLS is valid; OAuth callbacks and non-web DNS records (MX, SPF, DKIM, DMARC, verification TXT) are verified.
- [ ] Rollback to the preserved Replit deployment is exercised or documented with exact current deployment identifiers and data reconciliation steps.
- [ ] Production traffic cutover is reviewed and approved by the owner; Replit receives no production traffic after cutover and remains available through the rollback window.
- [ ] Replit retirement is a separate decision. Do not delete its deployment, database, secrets, generated files, or domain config until every gate in [REPLIT_REMOVAL_PLAN.md](./REPLIT_REMOVAL_PLAN.md) passes and the owner explicitly authorizes it.
