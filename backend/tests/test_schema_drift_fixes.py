"""Regression tests for the production schema drift found on 2026-11-18.

- The query builder sends dicts as JSON (agent_runs.metadata is jsonb), lists stay arrays.
- Tenant purge treats the legacy user_totp_mfa table as optional.
- DSAR access only reads columns production has.
- The migration creates everything the code selects.
"""

from __future__ import annotations

from pathlib import Path

from app.db import database
from app.routes import dsar_routes
from app.services.compliance import tenant_purge
from psycopg2.extras import Json

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20261118040000_restore_missing_schema.sql"
)


def test_dicts_are_sent_as_json_and_lists_as_arrays():
    adapted = database._adapt_value({"source": "mcp"})
    assert isinstance(adapted, Json) and adapted.adapted == {"source": "mcp"}
    assert database._adapt_value(["a", "b"]) == ["a", "b"]
    assert database._adapt_value("x") == "x" and database._adapt_value(None) is None


def test_legacy_totp_table_is_optional_in_purge():
    assert "user_totp_mfa" in tenant_purge.OPTIONAL_PURGE_TABLES


def test_dsar_reads_only_columns_production_has():
    source = Path(dsar_routes.__file__).read_text()
    assert "ip_hash" not in source
    assert "nickname AS label" in source
    assert "JOIN api_clients" in source


def test_migration_restores_what_the_code_selects():
    sql = MIGRATION.read_text()
    for needed in (
        "ADD COLUMN IF NOT EXISTS is_published",
        "public.user_sessions",
        "public.idea_collaborators",
        "UNIQUE (idea_id, user_id)",
        "public.rate_limit_events",
        "intellectual_properties (idea_id)",
        "ENABLE ROW LEVEL SECURITY",
    ):
        assert needed in sql, needed
    assert "DROP " not in sql.upper(), "this migration must stay additive"
