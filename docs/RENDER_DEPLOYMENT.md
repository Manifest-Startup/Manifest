# Render deployment (Manifest backend)

Render hosts the FastAPI backend behind the Cloudflare Worker. Replit remains the live production origin and rollback environment until the gates in [PRODUCTION_READINESS_CHECKLIST.md](./PRODUCTION_READINESS_CHECKLIST.md) pass.

## Blueprint

[`render.yaml`](../render.yaml) defines one free-plan production web service using [`backend/dockerfile`](../backend/dockerfile). The Render Blueprint has been planned in the Manifest workspace. Review the current plan in the Render Dashboard before applying it. Render may assign a different service name or hostname; use the actual `onrender.com` hostname as `BACKEND_ORIGIN` in [`wrangler.jsonc`](../deploy/cloudflare/wrangler.jsonc).

The web service still has a public Render hostname. `EDGE_SHARED_SECRET` must be set to the same random value on Render and the Worker before treating the origin as protected; the backend intentionally leaves health probes open.

## Environment variables

Set secret values in Render's Environment page. Do not put them in Git, this document, or chat. Copy only the values needed by this app from the preserved Replit deployment and Supabase project.

| Variable | Purpose |
|----------|---------|
| `EDGE_SHARED_SECRET` | Shared Worker-to-origin authentication secret; set the same value on Cloudflare. |
| `DATABASE_URL` | Supabase Postgres connection URL. |
| `SESSION_SECRET` | Render generates a fresh value; Replit sessions are not being imported. |
| `MANIFEST_KEK_PROVIDER`, `MANIFEST_KEK_ACTIVE_VERSION`, `MANIFEST_KEK_V1` | The Blueprint sets `env`, `1`, and generates a base64-encoded 256-bit key. |
| `MFA_ENCRYPTION_KEY` | Render generates a fresh value; Replit MFA records are not being imported. |
| `MANIFEST_PRIVACY_IP_HASH_SALT` | Render generates a fresh value; Replit privacy records are not being imported. |
| `OPENAI_API_KEY`, `GOOGLE_API_KEY` | AI generation providers. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Server-side Supabase Storage access. |
| `APP_BASE_URL`, `FRONTEND_ORIGINS` | Public Cloudflare URLs for reset links and CORS. Include apex and `www`. |
| `RESEND_API_KEY`, `RESEND_FROM_EMAIL` | Transactional email. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Optional Google OAuth integration. |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | Optional GitHub OAuth integration. |
| `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET` | Optional Slack OAuth integration. |
| `POSTHOG_API_KEY` | Optional analytics. |

The Blueprint also sets `ENVIRONMENT=production`, `LOG_FORMAT=json`, `WEB_CONCURRENCY=1`, `PORT=8000`, `UVICORN_FORWARDED_ALLOW_IPS=*`, and `AI_MODEL=gpt-4o-mini`. The wildcard forwarded-IP trust is safe only while `EDGE_SHARED_SECRET` is enabled and the guard rejects direct-origin requests. Do not copy Replit-only `REPL_ID`, `ISSUER_URL`, `REPLIT_DEV_DOMAIN`, or `REPLIT_DOMAINS` values. Replit OIDC login will not be available on Render; users can use the app's email/password flow or a configured provider login.

## Health and routing checks

After deploy, test the assigned Render URL:

```bash
curl -i https://YOUR-SERVICE.onrender.com/ping
curl -i https://YOUR-SERVICE.onrender.com/health
curl -i https://YOUR-SERVICE.onrender.com/healthz
```

Health probes should return 2xx. A protected route called directly at the Render hostname should return 403 without the edge secret. The same route through the Cloudflare Worker should succeed. Do not point production DNS at Cloudflare until data, file storage, authentication, API, Socket.IO, email, OAuth, AI, and rollback checks pass.

## Replit rollback

Keep the current Replit deployment, database, secrets, and files intact through the observation period. Follow [REPLIT_REMOVAL_PLAN.md](./REPLIT_REMOVAL_PLAN.md) only after the production checklist is complete and the owner explicitly authorizes retirement.
