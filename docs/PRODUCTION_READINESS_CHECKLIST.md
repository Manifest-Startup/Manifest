# Production readiness checklist

Complete before moving production traffic from Replit to the Cloudflare edge stack. Replit remains the rollback environment through the observation window; retirement has a separate approval gate in [REPLIT_REMOVAL_PLAN.md](./REPLIT_REMOVAL_PLAN.md).

## Source and deploy

- [ ] Migration branch changes are merged into GitHub `main`; CI is green on the exact deployed commit.
- [x] Cloudflare Worker `manifest-production` is deployed from `deploy/cloudflare/wrangler.jsonc` and serves the site at `manifeststartup.com` and `www.manifeststartup.com`.
- [x] Worker routes GraphQL, REST, auth, Socket.IO, health, generated-file and agent-discovery paths to the configured backend; SPA deep links load from edge assets.
- [x] The Render backend service created by the Manifest Blueprint is deployed from `main`; `/ping`, `/health`, and `/healthz` return 200.
- [ ] `EDGE_SHARED_SECRET` matches between Worker and Render; direct-origin protected requests are rejected and Worker-routed requests succeed.
- [ ] Render production secrets are set, including `DATABASE_URL`, `SESSION_SECRET`, Supabase credentials (no `OPENAI_API_KEY`: customers bring their own key), and every historical `MANIFEST_KEK_V<n>` needed to decrypt stored data.
- [ ] `FRONTEND_ORIGINS`, `APP_BASE_URL`, `BACKEND_ORIGIN`, and `FILES_PUBLIC_BASE` match the production domains and Supabase project.
- [ ] `/metrics` is scraped or blocked at the edge per [OBSERVABILITY_AND_SLO.md](./OBSERVABILITY_AND_SLO.md); production logs are visible and structured.

## Data and durable files

- [x] Replit Postgres rows were not imported (owner decision); Replit has since been retired. Users from the Replit era sign up again.
- [ ] Take a Supabase backup before deployment and confirm that the existing Supabase dataset is the intended starting dataset for the new backend.
- [x] All repository Supabase migrations are applied and the deployed schema matches the expected application schema.
- [x] Client-role grants are revoked (`20261114090000_lock_down_public_role_grants.sql` and `20261114200000_reconcile_schema_with_backend.sql`, applied 2026-11-14). Re-run the Supabase security advisors after every schema change.

## Production route verification

- [ ] Email signup/login/logout, session refresh, password reset, guest session and guest merge work.
- [ ] Idea CRUD, document generation, pitch deck, BMC, similar ideas and messaging work.
- [ ] REST, GraphQL, Socket.IO live updates, email delivery, OAuth/SSO callbacks, AI generation and background work pass on the public Cloudflare route.
- [ ] Generated PDF download and profile image upload/read work through the public route.
- [ ] Error tracking/analytics receive events; Cloudflare and Render logs/costs remain stable through the agreed observation window (at least seven days).

## DNS, rollback, and sign-off

- [x] Apex and `www` resolve to the Cloudflare Worker; TLS is valid; OAuth callbacks and non-web DNS records (MX, SPF, DKIM, DMARC, verification TXT) are verified.
- [x] Production traffic runs through Cloudflare to Render; Replit is retired (2026-11-14).
