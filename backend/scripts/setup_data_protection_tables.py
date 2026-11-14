"""
Setup tables for Task #12 — Data protection, encryption & secrets.

Adds:
- ``tenant_data_keys`` (per-tenant wrapped DEKs; deleting a row crypto-shreds
  every ciphertext encrypted under it).
- ``integrations`` ciphertext columns + key version metadata. Plaintext
  columns remain so the migration is online + reversible: the read path
  prefers the ciphertext when present and falls back to plaintext, which
  lets us deploy the schema before flipping the encryption feature flag.
- ``users.data_region`` and ``sso_tenant_configs.data_region`` for tenant
  data-residency pinning. ``DEFAULT 'us'`` matches today's behaviour.

Idempotent. Safe to run repeatedly.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import get_db_connection
from app.utils.logger import logger


DDL_STATEMENTS = [
    # ---- envelope-encryption: per-tenant wrapped DEK store -----------------
    """
    CREATE TABLE IF NOT EXISTS tenant_data_keys (
        id BIGSERIAL PRIMARY KEY,
        tenant_kind TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        wrapped_dek BYTEA NOT NULL,
        kek_version INTEGER NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        revoked_at TIMESTAMP WITH TIME ZONE,
        UNIQUE (tenant_kind, tenant_id, kek_version)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_tenant_data_keys_lookup ON tenant_data_keys(tenant_kind, tenant_id) WHERE revoked_at IS NULL",
    # ---- integrations field-level encryption columns ----------------------
    """
    ALTER TABLE integrations
        ADD COLUMN IF NOT EXISTS access_token_ciphertext BYTEA,
        ADD COLUMN IF NOT EXISTS refresh_token_ciphertext BYTEA,
        ADD COLUMN IF NOT EXISTS token_key_version INTEGER
    """,
    # ---- data residency pinning -------------------------------------------
    """
    ALTER TABLE users
        ADD COLUMN IF NOT EXISTS data_region TEXT NOT NULL DEFAULT 'us'
    """,
    "CREATE INDEX IF NOT EXISTS idx_users_data_region ON users(data_region)",
    """
    ALTER TABLE sso_tenant_configs
        ADD COLUMN IF NOT EXISTS data_region TEXT NOT NULL DEFAULT 'us'
    """,
    # ---- backup verification ledger ---------------------------------------
    """
    CREATE TABLE IF NOT EXISTS backup_integrity_checks (
        id BIGSERIAL PRIMARY KEY,
        backup_id TEXT NOT NULL,
        backup_taken_at TIMESTAMP WITH TIME ZONE NOT NULL,
        sha256 TEXT NOT NULL,
        size_bytes BIGINT NOT NULL,
        verified_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        verified_by TEXT NOT NULL,
        restore_drill_run_id TEXT,
        notes TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_backup_integrity_taken_at ON backup_integrity_checks(backup_taken_at DESC)",
]


def setup_data_protection_tables() -> None:
    with get_db_connection() as conn:
        cur = conn.cursor()
        for stmt in DDL_STATEMENTS:
            try:
                cur.execute(stmt)
                logger.info("[data_protection] applied: %s", stmt.strip().split("\n")[0][:80])
            except Exception as exc:
                logger.error("[data_protection] DDL failed: %s — %s", stmt[:80], exc)
                raise
        conn.commit()
    logger.info("[data_protection] All data-protection migrations applied.")


if __name__ == "__main__":
    setup_data_protection_tables()
