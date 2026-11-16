# Replit to Cloudflare migration

Manifest moves off Replit onto a low-cost stack with Cloudflare as the only public entry point.

```
browser / iOS app
      │  https://manifeststartup.com  (Cloudflare DNS + TLS, free)
      ▼
Cloudflare Worker `manifest-production`  (deploy/cloudflare, Workers Free)
  ├─ React build (frontend/build) served as static assets from the edge
  ├─ /generated/pdfs/*  → Supabase Storage public URLs (legacy file links)
  └─ /graphql /socket.io /api /auth /scim /trust /ping /health*  → BACKEND_ORIGIN
                                                                     │
                                         FastAPI Docker image (backend/Dockerfile)
                                         on Render free: `manifest-backend`
                                                                     │
                                         Supabase (free): Postgres + Storage
```

## Why this shape

- **Free.** Cloudflare Workers Free, Render free and Supabase free cost $0. Cloudflare Containers would run the backend on Cloudflare too, but they need Workers Paid (about $5/month plus usage).
- **No lock-in.** The backend is the same Docker image on any container host. To move it, deploy the image elsewhere and change `BACKEND_ORIGIN` in `deploy/cloudflare/wrangler.jsonc`. DNS, TLS, the site and every public URL stay the same.
- **Cold starts are kept low.** Render free sleeps after 15 idle minutes. The Worker's `*/10 * * * *` cron pings `/ping` to keep it warm, which fits the 750 free instance-hours a month for one service. The static site loads from the edge even while the backend wakes.
- **Durable files.** Render's disk is ephemeral. PDFs, pitch reels and profile pictures go to Supabase Storage when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set. Old `/generated/pdfs/<bucket>/<path>` links keep working because the Worker maps them to `FILES_PUBLIC_BASE`.

To upgrade later, either move the Render service to a paid plan (always on, no cron needed) or switch to Cloudflare Containers. In both cases only `BACKEND_ORIGIN` changes.

## Runbook

Order matters: keep Replit serving production until step 6.

### 1. Supabase project (existing destination)

Use the existing Manifest Supabase project (`lvwmgkgokmaxgecvkwap`) as the persistent database. Do not create a second project for this migration.

### 2. Replit data import (intentionally skipped)

By the owner's explicit decision, this cutover does **not** copy Replit Postgres rows. Keep the Replit database intact for rollback, and do not run `scripts/migrate_replit_to_supabase.py database` or any `--replace` command. The Render backend will use the existing Supabase database as-is; only the records already there will be available after cutover. Replit accounts, workspaces, and ideas absent from Supabase will not appear in the new deployment, and users may need to create accounts again. Replit-generated files are a separate transfer step; they remain on Replit for now. Since their database references are not being copied, decide separately whether those files need to be made accessible in the new deployment. The read-only `check` command can be used later if the owner wants to reconsider the database decision.

The Render `DATABASE_URL` must still point to the existing Supabase Postgres connection string (Settings → Database → session pooler). `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are separately used for Storage.

### 3. Backend on Render (owner + agent)

1. In Render, choose **New → Blueprint** and select this repository. That creates only `manifest-backend` (free).
2. Generate one random edge secret (`openssl rand -hex 32`) and set it as `EDGE_SHARED_SECRET` on both Render and the Worker (`npx wrangler secret put EDGE_SHARED_SECRET`). The backend then rejects any request that did not come through the Worker (only `/ping` and `/health*` stay open). That also makes the forwarded client IP trustworthy for rate limiting.
3. Set `DATABASE_URL` to the existing Supabase session-pooler URL. Render generates fresh values for `SESSION_SECRET`, `MANIFEST_KEK_V1`, and `MANIFEST_PRIVACY_IP_HASH_SALT`; the Blueprint sets `MANIFEST_KEK_PROVIDER=env` and `MANIFEST_KEK_ACTIVE_VERSION=1`. No Replit rows or sessions are imported, so do not reuse old Replit encryption keys. Copy provider API keys only for integrations you want enabled; OAuth and analytics credentials can remain unset if those features are not being used.
4. Wait for `/ping` to return 200 at the hostname shown for the planned Render service (currently `https://manifest-backend-dz6t.onrender.com/ping`). If Render assigns another hostname when the Blueprint is applied, update `BACKEND_ORIGIN` in `deploy/cloudflare/wrangler.jsonc` before deploying the Worker.

### 4. Edge Worker (agent)

Use Node 22 or newer:

```bash
cd deploy/cloudflare
npm ci && npm test
npm run build:frontend
npx wrangler deploy            # → https://manifest-production.<account>.workers.dev
```

Set `FILES_PUBLIC_BASE` to `https://<ref>.supabase.co/storage/v1/object/public`. Then smoke-test the workers.dev URL: signup, login, guest session, GraphQL, Socket.IO live updates, AI generation, PDF download and profile picture upload.

### 5. DNS (owner)

1. In the Cloudflare dashboard, choose **Add a domain** and enter `manifeststartup.com` (Free plan). Cloudflare imports the existing DNS records. Confirm that MX, SPF, DKIM, DMARC and verification TXT records are all present before continuing.
2. At the registrar (Squarespace, formerly Google Domains), replace the four `ns-cloud-e*.googledomains.com` nameservers with the two Cloudflare ones.
3. When the zone is **Active**, add `manifeststartup.com` and `www.manifeststartup.com` as **Custom Domains** on the `manifest-production` Worker. Remove the old Replit apex `A`/`TXT` records.
4. Update OAuth provider callback URLs if any still point at a `*.replit.app` host.

### 6. Observe, then retire Replit

Keep the Replit deployment paused but intact, with a final database backup, through the observation window (at least 7 days of clean logs). Then follow [REPLIT_REMOVAL_PLAN.md](./REPLIT_REMOVAL_PLAN.md).

**Rollback:** in Cloudflare DNS, point the apex back to Replit's IP and TXT record (or restore the registrar nameservers), then reconcile writes made during the Cloudflare window.

## Known limits

- The SPA shell is now served statically. Per-route meta tags and CSP nonces that the backend added to `index.html` are not applied to edge-served pages. The CSP was report-only, and the Worker can add this later if SEO needs it.
- `frontend/public/videos/founders-video.mov` (77 MB) is unreferenced and excluded from the edge upload by `.assetsignore`, because Workers assets are limited to 25 MiB per file.
- Render free has one instance and no background-worker services. The optional durable job worker (`app.workers.generation_worker`) is not deployed; the UI does not use `enqueueBackgroundTasks` yet.
