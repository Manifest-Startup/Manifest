#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Refresh the local copy of the Postgres schema (migrations only) from the
# live Supabase project using the Supabase CLI.
#
# Usage:
#   ./scripts/update_db_schema.sh
#
# The script assumes you have:
#   • Run `supabase login` at least once (or set SUPABASE_ACCESS_TOKEN)
#   • Populated `supabase/config.toml` with your project_id.
# -----------------------------------------------------------------------------

set -euo pipefail
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_ROOT"

if ! command -v supabase &> /dev/null; then
  echo "Error: Supabase CLI is not installed. See https://supabase.com/docs/guides/cli." >&2
  exit 1
fi

SCHEMAS="public,auth,storage,graphql_public"

if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker is not running. Please start Docker Desktop first." >&2
  exit 1
fi

echo "📥  Pulling schema for schemas: $SCHEMAS …"
supabase db pull --schema "$SCHEMAS"

echo "✅  supabase/migrations directory updated.  Remember to commit any new or changed migration files." 