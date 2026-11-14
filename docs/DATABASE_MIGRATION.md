# Database migration (Replit Postgres → staging → Supabase)

Production data today lives on **Replit-managed Postgres**. The repo’s canonical schema migrations live in [`supabase/migrations/`](../supabase/migrations/) and target **Supabase** for the long-term production database.

**Do not point Render staging at live Replit Postgres for write tests.** Clone data to an isolated staging database first.

## Phase A — Discover Replit production database

In the Replit project dashboard:

1. Open **Secrets** / **Database** and locate `DATABASE_URL` (or Replit Postgres connection string).
2. Record (do not commit):
   - Postgres version
   - Database name and host
   - Whether extensions exist (`uuid-ossp`, `pgcrypto`, etc.)
3. Export schema-only for comparison:

```bash
pg_dump "$REPLIT_DATABASE_URL" --schema-only --no-owner --no-privileges > replit_schema.sql
```

Compare tables to [`supabase/migrations/`](../supabase/migrations/) — expect drift until migrations are applied to staging.

## Phase B — Create staging Postgres

Choose one:

| Provider | Use case |
|----------|----------|
| **Render Postgres** | Same vendor as backend staging; easy private networking |
| **Supabase dev project** | Exercises migration path early (`supabase/config.toml` project ref) |

Create an empty database and set `DATABASE_URL` on **Render staging only**.

## Phase C — Clone Replit → staging (read-only export window)

```bash
# Export from Replit (maintenance window or read replica if available)
pg_dump "$REPLIT_DATABASE_URL" \
  --format=custom \
  --no-owner \
  --no-privileges \
  -f manifest_replit_backup.dump

# Restore to staging
pg_restore --dbname="$STAGING_DATABASE_URL" \
  --no-owner \
  --no-privileges \
  --clean \
  --if-exists \
  manifest_replit_backup.dump
```

Verify row counts on critical tables: `users`, `ideas`, `documents`, `pitch_reels`, `conversations`.

## Phase D — Apply Supabase migrations to staging

With [Supabase CLI](https://supabase.com/docs/guides/cli) linked to the staging project:

```bash
supabase db push --db-url "$STAGING_DATABASE_URL"
# or apply migrations manually and resolve drift
supabase migration list
```

Run Supabase advisors / security review per [`SUPABASE_SECURITY.md`](./SUPABASE_SECURITY.md).

Fix any migration failures on **staging only** before touching production.

## Phase E — Pre-cutover (Replit → Supabase production)

When parallel QA passes on Render + Vercel + staging DB:

1. Schedule maintenance window for production cutover.
2. Final `pg_dump` from Replit Postgres.
3. Restore to **Supabase production** project.
4. Apply all migrations; run advisors again.
5. Update Render production `DATABASE_URL` to Supabase.
6. Keep Replit Postgres **read-only backup** for 30+ days.

Adapt or reverse [`scripts/migrate_from_supabase.py`](../scripts/migrate_from_supabase.py) if you need table-level export/import instead of `pg_dump`.

## Safe errors when misconfigured

The backend already fails fast in production-like environments when:

- `SESSION_SECRET` is missing
- `DATABASE_URL` is unset → demo/in-memory mode (non-prod only)

After cutover, ensure `DATABASE_URL` is always set on Render production so demo mode cannot activate.

## Secrets

Never commit connection strings. Store in:

- Replit Secrets (unchanged until decommission)
- Render Environment
- Supabase project settings

See [`.env.example`](../.env.example) for variable names.
