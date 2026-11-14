-- Reconcile Supabase with the schema the backend expects.
-- The Replit database gained these columns/tables through backend/scripts/setup_*.py
-- and manual changes that never became migrations. Every statement is additive
-- and idempotent (IF NOT EXISTS); nothing is dropped or rewritten.

-- base users columns read by password/OAuth login and account deletion (never had a migration)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS password_hash TEXT,
    ADD COLUMN IF NOT EXISTS auth_provider TEXT NOT NULL DEFAULT 'email',
    ADD COLUMN IF NOT EXISTS replit_id TEXT,
    ADD COLUMN IF NOT EXISTS deletion_requested_at TIMESTAMP WITH TIME ZONE;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_replit_id ON users(replit_id) WHERE replit_id IS NOT NULL;

-- backend/scripts/setup_api_tables.py
CREATE TABLE IF NOT EXISTS api_clients (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL,
                name VARCHAR(255) NOT NULL,
                tier VARCHAR(50) DEFAULT 'free',
                status VARCHAR(50) DEFAULT 'active',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_used_at TIMESTAMP WITH TIME ZONE,
                metadata JSONB DEFAULT '{}'::jsonb
            );
            
            CREATE INDEX IF NOT EXISTS idx_api_clients_user_id ON api_clients(user_id);
            CREATE INDEX IF NOT EXISTS idx_api_clients_status ON api_clients(status);
CREATE TABLE IF NOT EXISTS api_keys (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES api_clients(id) ON DELETE CASCADE,
                name VARCHAR(255) DEFAULT 'Default Key',
                key_prefix VARCHAR(20) NOT NULL,
                key_hash VARCHAR(64) NOT NULL,
                status VARCHAR(50) DEFAULT 'active',
                expires_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_used_at TIMESTAMP WITH TIME ZONE,
                revoked_at TIMESTAMP WITH TIME ZONE,
                UNIQUE(key_prefix, key_hash)
            );
            
            CREATE INDEX IF NOT EXISTS idx_api_keys_client_id ON api_keys(client_id);
            CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);
            CREATE INDEX IF NOT EXISTS idx_api_keys_status ON api_keys(status);
CREATE TABLE IF NOT EXISTS api_usage_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES api_clients(id) ON DELETE CASCADE,
                key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
                endpoint VARCHAR(255) NOT NULL,
                response_code INTEGER NOT NULL,
                latency_ms INTEGER,
                tokens_used INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                metadata JSONB DEFAULT '{}'::jsonb
            );
            
            CREATE INDEX IF NOT EXISTS idx_api_usage_events_client_id ON api_usage_events(client_id);
            CREATE INDEX IF NOT EXISTS idx_api_usage_events_created_at ON api_usage_events(created_at);
CREATE TABLE IF NOT EXISTS api_usage_daily (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES api_clients(id) ON DELETE CASCADE,
                date DATE NOT NULL,
                request_count INTEGER DEFAULT 0,
                tokens_used INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(client_id, date)
            );
            
            CREATE INDEX IF NOT EXISTS idx_api_usage_daily_client_id ON api_usage_daily(client_id);
            CREATE INDEX IF NOT EXISTS idx_api_usage_daily_date ON api_usage_daily(date);

-- backend/scripts/setup_security_hardening_tables.py
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
        ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'member';
CREATE INDEX IF NOT EXISTS idx_users_disabled ON users(disabled_at) WHERE disabled_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin) WHERE is_admin = TRUE;
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE TABLE IF NOT EXISTS account_lockouts (
        id BIGSERIAL PRIMARY KEY,
        bucket_key TEXT NOT NULL,
        bucket_kind TEXT NOT NULL CHECK (bucket_kind IN ('email','ip','user_id')),
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until TIMESTAMP WITH TIME ZONE,
        first_failure_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        last_failure_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        UNIQUE(bucket_kind, bucket_key)
    );
CREATE INDEX IF NOT EXISTS idx_account_lockouts_locked_until ON account_lockouts(locked_until);
CREATE TABLE IF NOT EXISTS password_history (
        id BIGSERIAL PRIMARY KEY,
        user_id UUID NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    );
CREATE INDEX IF NOT EXISTS idx_password_history_user ON password_history(user_id, created_at DESC);
ALTER TABLE api_keys
        ADD COLUMN IF NOT EXISTS scopes TEXT[] NOT NULL DEFAULT ARRAY['read']::TEXT[],
        ADD COLUMN IF NOT EXISTS hash_algo VARCHAR(16) NOT NULL DEFAULT 'sha256',
        ADD COLUMN IF NOT EXISTS rotated_to UUID,
        ADD COLUMN IF NOT EXISTS last_used_ip INET,
        ADD COLUMN IF NOT EXISTS last_rotated_at TIMESTAMP WITH TIME ZONE,
        ALTER COLUMN key_hash TYPE TEXT;
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
    );
CREATE INDEX IF NOT EXISTS idx_step_up_user_active ON step_up_verifications(user_id, expires_at) WHERE revoked_at IS NULL;
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
    );
CREATE INDEX IF NOT EXISTS idx_webauthn_user ON webauthn_credentials(user_id) WHERE revoked_at IS NULL;
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
    );
CREATE INDEX IF NOT EXISTS idx_sso_tenant_domain ON sso_tenant_configs(email_domain) WHERE disabled_at IS NULL;
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
    );
CREATE INDEX IF NOT EXISTS idx_scim_groups_tenant ON scim_groups(tenant_id) WHERE deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS scim_group_members (
        group_id UUID NOT NULL REFERENCES scim_groups(group_id) ON DELETE CASCADE,
        user_id UUID NOT NULL,
        added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        PRIMARY KEY (group_id, user_id)
    );
CREATE INDEX IF NOT EXISTS idx_scim_group_members_user ON scim_group_members(user_id);
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
    );
CREATE INDEX IF NOT EXISTS idx_admin_audit_actor ON admin_audit_events(actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_action ON admin_audit_events(action, created_at DESC);
CREATE TABLE IF NOT EXISTS saml_processed_assertions (
        assertion_id TEXT PRIMARY KEY,
        tenant_slug TEXT NOT NULL,
        processed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    );
CREATE INDEX IF NOT EXISTS idx_saml_replay_processed_at ON saml_processed_assertions(processed_at);

-- backend/scripts/setup_data_protection_tables.py
CREATE TABLE IF NOT EXISTS tenant_data_keys (
        id BIGSERIAL PRIMARY KEY,
        tenant_kind TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        wrapped_dek BYTEA NOT NULL,
        kek_version INTEGER NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        revoked_at TIMESTAMP WITH TIME ZONE,
        UNIQUE (tenant_kind, tenant_id, kek_version)
    );
CREATE INDEX IF NOT EXISTS idx_tenant_data_keys_lookup ON tenant_data_keys(tenant_kind, tenant_id) WHERE revoked_at IS NULL;
ALTER TABLE integrations
        ADD COLUMN IF NOT EXISTS access_token_ciphertext BYTEA,
        ADD COLUMN IF NOT EXISTS refresh_token_ciphertext BYTEA,
        ADD COLUMN IF NOT EXISTS token_key_version INTEGER;
ALTER TABLE users
        ADD COLUMN IF NOT EXISTS data_region TEXT NOT NULL DEFAULT 'us';
CREATE INDEX IF NOT EXISTS idx_users_data_region ON users(data_region);
ALTER TABLE sso_tenant_configs
        ADD COLUMN IF NOT EXISTS data_region TEXT NOT NULL DEFAULT 'us';
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
    );
CREATE INDEX IF NOT EXISTS idx_backup_integrity_taken_at ON backup_integrity_checks(backup_taken_at DESC);

-- backend/scripts/setup_audit_chain_tables.py
CREATE TABLE IF NOT EXISTS security_audit_events (
        event_id    UUID PRIMARY KEY,
        event_type  VARCHAR(255) NOT NULL,
        user_id     TEXT,
        request_ip  TEXT,
        session_id  TEXT,
        metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
    );
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS seq BIGSERIAL;
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'security';
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS severity TEXT NOT NULL DEFAULT 'info';
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS sensitivity TEXT NOT NULL DEFAULT 'internal';
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS request_id TEXT;
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS actor_id TEXT;
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS actor_type TEXT;
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS action TEXT;
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS target_type TEXT;
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS target_id TEXT;
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS user_agent TEXT;
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS outcome TEXT;
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS prev_hash TEXT;
ALTER TABLE security_audit_events ADD COLUMN IF NOT EXISTS event_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_sae_seq ON security_audit_events(seq);
CREATE INDEX IF NOT EXISTS idx_sae_event_type_created ON security_audit_events(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sae_user_created ON security_audit_events(user_id, created_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sae_severity_created ON security_audit_events(severity, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sae_event_hash_unique ON security_audit_events(event_hash) WHERE event_hash IS NOT NULL;

-- backend/scripts/setup_dsar_workflow_tables.py
CREATE TABLE IF NOT EXISTS dsar_requests (
        id              UUID PRIMARY KEY,
        type            TEXT NOT NULL,
        subject_user_id TEXT,
        subject_email   TEXT,
        jurisdiction    TEXT,
        status          TEXT NOT NULL DEFAULT 'open',
        assignee        TEXT,
        received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        due_at          TIMESTAMPTZ NOT NULL,
        completed_at    TIMESTAMPTZ,
        sla_days        INT NOT NULL,
        notes           TEXT,
        evidence        JSONB NOT NULL DEFAULT '[]'::jsonb,
        audit_event_id  UUID,
        created_by      TEXT
    );
CREATE INDEX IF NOT EXISTS idx_dsar_requests_status ON dsar_requests(status, due_at);
CREATE INDEX IF NOT EXISTS idx_dsar_requests_subject ON dsar_requests(subject_user_id) WHERE subject_user_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS incident_breach_timers (
        id                   UUID PRIMARY KEY,
        incident_id          TEXT NOT NULL,
        kind                 TEXT NOT NULL,
        opened_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        deadline_at          TIMESTAMPTZ NOT NULL,
        notified_at          TIMESTAMPTZ,
        regulator            TEXT,
        affected_count       INT,
        affected_jurisdiction TEXT,
        notes                TEXT,
        status               TEXT NOT NULL DEFAULT 'open',
        closed_at            TIMESTAMPTZ
    );
CREATE INDEX IF NOT EXISTS idx_incident_breach_open ON incident_breach_timers(status, deadline_at);
CREATE INDEX IF NOT EXISTS idx_incident_breach_incident ON incident_breach_timers(incident_id);
