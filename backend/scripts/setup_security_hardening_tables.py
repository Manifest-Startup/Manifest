"""
Setup tables and columns for Task #11 — Identity, access & session hardening.

Adds:
- users.is_admin / users.must_change_password / users.failed_login_count
- account_lockouts (per-email + per-IP exponential backoff)
- password_history (prevents reuse of last N passwords)
- api_keys.scopes / api_keys.rotated_to / api_keys.last_used_ip / api_keys.hash_algo
- step_up_verifications (recent re-auth proofs for sensitive ops)
- webauthn_credentials (passkey storage)
- sso_tenant_configs (per-tenant SAML/OIDC SSO config)
- sso_jit_link (links external IdP subjects to local user_ids)
- admin_audit_events (separate trail required by SEC-066)

Idempotent. Safe to run repeatedly.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import get_db_connection
from app.utils.logger import logger


DDL_STATEMENTS = [
    # users hardening
    """
    ALTER TABLE users
        ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS failed_login_count INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS last_failed_login_at TIMESTAMP WITH TIME ZONE,
        ADD COLUMN IF NOT EXISTS mfa_required BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS sso_tenant_id UUID,
        ADD COLUMN IF NOT EXISTS sso_subject TEXT,
        ADD COLUMN IF NOT EXISTS disabled_at TIMESTAMP WITH TIME ZONE,
        ADD COLUMN IF NOT EXISTS disabled_reason TEXT,
        ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'member'
    """,
    "CREATE INDEX IF NOT EXISTS idx_users_disabled ON users(disabled_at) WHERE disabled_at IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin) WHERE is_admin = TRUE",
    "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)",
    # account lockouts
    """
    CREATE TABLE IF NOT EXISTS account_lockouts (
        id BIGSERIAL PRIMARY KEY,
        bucket_key TEXT NOT NULL,
        bucket_kind TEXT NOT NULL CHECK (bucket_kind IN ('email','ip','user_id')),
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until TIMESTAMP WITH TIME ZONE,
        first_failure_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        last_failure_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        UNIQUE(bucket_kind, bucket_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_account_lockouts_locked_until ON account_lockouts(locked_until)",
    # password history
    """
    CREATE TABLE IF NOT EXISTS password_history (
        id BIGSERIAL PRIMARY KEY,
        user_id UUID NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_password_history_user ON password_history(user_id, created_at DESC)",
    # api_keys hardening
    """
    ALTER TABLE api_keys
        ADD COLUMN IF NOT EXISTS scopes TEXT[] NOT NULL DEFAULT ARRAY['read']::TEXT[],
        ADD COLUMN IF NOT EXISTS hash_algo VARCHAR(16) NOT NULL DEFAULT 'sha256',
        ADD COLUMN IF NOT EXISTS rotated_to UUID,
        ADD COLUMN IF NOT EXISTS last_used_ip INET,
        ADD COLUMN IF NOT EXISTS last_rotated_at TIMESTAMP WITH TIME ZONE,
        ALTER COLUMN key_hash TYPE TEXT
    """,
    # step-up auth proofs (short-lived)
    """
    CREATE TABLE IF NOT EXISTS step_up_verifications (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL,
        session_id UUID,
        method VARCHAR(32) NOT NULL,
        verified_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        revoked_at TIMESTAMP WITH TIME ZONE,
        request_ip INET,
        user_agent TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_step_up_user_active ON step_up_verifications(user_id, expires_at) WHERE revoked_at IS NULL",
    # webauthn credentials
    """
    CREATE TABLE IF NOT EXISTS webauthn_credentials (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL,
        credential_id BYTEA NOT NULL UNIQUE,
        public_key BYTEA NOT NULL,
        sign_count BIGINT NOT NULL DEFAULT 0,
        transports TEXT[],
        aaguid UUID,
        nickname TEXT,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        last_used_at TIMESTAMP WITH TIME ZONE,
        revoked_at TIMESTAMP WITH TIME ZONE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_webauthn_user ON webauthn_credentials(user_id) WHERE revoked_at IS NULL",
    # sso tenant config
    """
    CREATE TABLE IF NOT EXISTS sso_tenant_configs (
        tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        slug TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL,
        protocol VARCHAR(16) NOT NULL CHECK (protocol IN ('saml','oidc')),
        email_domain TEXT NOT NULL,
        idp_entity_id TEXT,
        idp_sso_url TEXT,
        idp_x509_cert TEXT,
        oidc_issuer TEXT,
        oidc_client_id TEXT,
        oidc_client_secret_encrypted BYTEA,
        scim_token_hash TEXT,
        jit_provisioning BOOLEAN NOT NULL DEFAULT TRUE,
        require_mfa BOOLEAN NOT NULL DEFAULT TRUE,
        default_role TEXT NOT NULL DEFAULT 'member',
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        disabled_at TIMESTAMP WITH TIME ZONE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sso_tenant_domain ON sso_tenant_configs(email_domain) WHERE disabled_at IS NULL",
    # SCIM groups (per-tenant) and group membership.
    """
    CREATE TABLE IF NOT EXISTS scim_groups (
        group_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL,
        external_id TEXT,
        display_name TEXT NOT NULL,
        mapped_role TEXT,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        deleted_at TIMESTAMP WITH TIME ZONE,
        UNIQUE (tenant_id, display_name)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_scim_groups_tenant ON scim_groups(tenant_id) WHERE deleted_at IS NULL",
    """
    CREATE TABLE IF NOT EXISTS scim_group_members (
        group_id UUID NOT NULL REFERENCES scim_groups(group_id) ON DELETE CASCADE,
        user_id UUID NOT NULL,
        added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        PRIMARY KEY (group_id, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_scim_group_members_user ON scim_group_members(user_id)",
    # admin audit events (separation from generic security events for SEC-066)
    """
    CREATE TABLE IF NOT EXISTS admin_audit_events (
        event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        actor_user_id UUID NOT NULL,
        target_user_id UUID,
        action VARCHAR(64) NOT NULL,
        resource VARCHAR(64),
        request_ip INET,
        user_agent TEXT,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        step_up_verification_id UUID,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_admin_audit_actor ON admin_audit_events(actor_user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_admin_audit_action ON admin_audit_events(action, created_at DESC)",
    # SAML assertion replay protection
    """
    CREATE TABLE IF NOT EXISTS saml_processed_assertions (
        assertion_id TEXT PRIMARY KEY,
        tenant_slug TEXT NOT NULL,
        processed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_saml_replay_processed_at ON saml_processed_assertions(processed_at)",
]


def setup_security_hardening_tables() -> None:
    with get_db_connection() as conn:
        cur = conn.cursor()
        for stmt in DDL_STATEMENTS:
            try:
                cur.execute(stmt)
                logger.info("[security_hardening] applied: %s", stmt.strip().split("\n")[0][:80])
            except Exception as exc:
                logger.error("[security_hardening] DDL failed: %s — %s", stmt[:80], exc)
                raise
        conn.commit()
    logger.info("[security_hardening] All security hardening migrations applied.")


if __name__ == "__main__":
    setup_security_hardening_tables()
