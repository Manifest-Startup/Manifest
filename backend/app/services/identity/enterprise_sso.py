"""Enterprise SSO config service (SAML 2.0 + OIDC) — scaffolding.

Provides the data layer for ``sso_tenant_configs``. Identity-provider
specific verification (SAML response signature checks; OIDC token
verification) is delegated:

- OIDC: handled by ``app.security.oidc_verification.verify_id_token``.
- SAML: requires ``python3-saml`` for production-grade response validation.
  This module ships the config storage and JIT-provisioning helpers; the
  POST-binding SAML response handler in ``backend/app/routes/sso_routes.py``
  is gated behind a feature flag (``ENABLE_SAML_SSO``) until the dependency
  is added and tenant-specific certificates are loaded into KMS.

Until SAML is fully enabled, the OIDC path is fully functional and any
enterprise customer can be onboarded by registering a tenant config with
``protocol='oidc'`` pointing at their issuer (Okta, Azure AD, Auth0, etc.).
"""

from __future__ import annotations

import os
import secrets
from typing import Any

from app.db.database import get_db_connection
from app.utils.logger import logger


def _domain_from_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.split("@", 1)[1].strip().lower()


def find_tenant_for_email(email: str) -> dict[str, Any] | None:
    """Look up the SSO tenant a given email should authenticate against."""
    domain = _domain_from_email(email)
    if not domain:
        return None
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT * FROM sso_tenant_configs
                    WHERE email_domain = %s AND disabled_at IS NULL
                    LIMIT 1
                    """,
                (domain,),
            )
            return cur.fetchone()
    except Exception as exc:
        logger.debug("[sso] tenant lookup failed for %s: %s", domain, exc)
        return None


def list_tenants() -> list[dict[str, Any]]:
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id, slug, display_name, protocol, email_domain, "
                "require_mfa, jit_provisioning, disabled_at, created_at "
                "FROM sso_tenant_configs ORDER BY created_at DESC"
            )
            return cur.fetchall() or []
    except Exception as exc:
        logger.warning("[sso] list_tenants failed: %s", exc)
        return []


def upsert_tenant(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Create or update a tenant config. SCIM token (if provided in payload as
    ``scim_token``) is hashed before persistence."""
    required = {"slug", "display_name", "protocol", "email_domain"}
    missing = required - set(payload.keys())
    if missing:
        raise ValueError(f"Missing required SSO fields: {', '.join(sorted(missing))}")
    if payload["protocol"] not in {"saml", "oidc"}:
        raise ValueError("protocol must be 'saml' or 'oidc'")

    scim_token_hash = None
    if payload.get("scim_token"):
        import hashlib

        scim_token_hash = hashlib.sha256(payload["scim_token"].encode()).hexdigest()

    # Residency gate (Task #12). If the caller pinned a region for this
    # tenant, refuse to write it on a process serving a different region.
    if payload.get("data_region"):
        from app.security.data_residency import (
            RegionMismatchError,
            assert_region_match,
        )

        try:
            assert_region_match(payload["data_region"], context="sso_tenant_configs.upsert")
        except RegionMismatchError:
            logger.error(
                "[sso] upsert_tenant blocked by data residency for slug=%s",
                payload.get("slug"),
            )
            return None

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sso_tenant_configs (
                        slug, display_name, protocol, email_domain,
                        idp_entity_id, idp_sso_url, idp_x509_cert,
                        oidc_issuer, oidc_client_id,
                        scim_token_hash, jit_provisioning, require_mfa, default_role
                    ) VALUES (
                        %(slug)s, %(display_name)s, %(protocol)s, %(email_domain)s,
                        %(idp_entity_id)s, %(idp_sso_url)s, %(idp_x509_cert)s,
                        %(oidc_issuer)s, %(oidc_client_id)s,
                        %(scim_token_hash)s, %(jit_provisioning)s, %(require_mfa)s, %(default_role)s
                    )
                    ON CONFLICT (slug) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        protocol = EXCLUDED.protocol,
                        email_domain = EXCLUDED.email_domain,
                        idp_entity_id = EXCLUDED.idp_entity_id,
                        idp_sso_url = EXCLUDED.idp_sso_url,
                        idp_x509_cert = EXCLUDED.idp_x509_cert,
                        oidc_issuer = EXCLUDED.oidc_issuer,
                        oidc_client_id = EXCLUDED.oidc_client_id,
                        scim_token_hash = COALESCE(EXCLUDED.scim_token_hash, sso_tenant_configs.scim_token_hash),
                        jit_provisioning = EXCLUDED.jit_provisioning,
                        require_mfa = EXCLUDED.require_mfa,
                        default_role = EXCLUDED.default_role,
                        updated_at = NOW()
                    RETURNING tenant_id, slug, display_name, protocol, email_domain,
                              jit_provisioning, require_mfa
                    """,
                    {
                        "slug": payload["slug"],
                        "display_name": payload["display_name"],
                        "protocol": payload["protocol"],
                        "email_domain": payload["email_domain"].strip().lower(),
                        "idp_entity_id": payload.get("idp_entity_id"),
                        "idp_sso_url": payload.get("idp_sso_url"),
                        "idp_x509_cert": payload.get("idp_x509_cert"),
                        "oidc_issuer": payload.get("oidc_issuer"),
                        "oidc_client_id": payload.get("oidc_client_id"),
                        "scim_token_hash": scim_token_hash,
                        "jit_provisioning": bool(payload.get("jit_provisioning", True)),
                        "require_mfa": bool(payload.get("require_mfa", True)),
                        "default_role": payload.get("default_role", "member"),
                    },
                )
                row = cur.fetchone()
            conn.commit()
        return row
    except Exception as exc:
        logger.error("[sso] upsert_tenant failed: %s", exc)
        raise


def jit_provision_user(
    *,
    tenant: dict[str, Any],
    subject: str,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> str | None:
    """Look up an existing user by sso_subject; create one if JIT is enabled.

    Returns the user_id on success, ``None`` on failure or when a user
    must be created but JIT is disabled.
    """
    if not tenant or not subject or not email:
        return None
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id FROM users WHERE sso_tenant_id = %s AND sso_subject = %s",
                    (tenant["tenant_id"], subject),
                )
                existing = cur.fetchone()
                if existing:
                    return str(existing["user_id"])
                if not tenant.get("jit_provisioning"):
                    return None
                cur.execute(
                    """
                    INSERT INTO users (
                        email, first_name, last_name, auth_provider,
                        sso_tenant_id, sso_subject,
                        mfa_required, created_at
                    )
                    VALUES (%s, %s, %s, 'sso', %s, %s, %s, NOW())
                    RETURNING user_id
                    """,
                    (
                        email.lower(),
                        first_name,
                        last_name,
                        tenant["tenant_id"],
                        subject,
                        bool(tenant.get("require_mfa", True)),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return str(row["user_id"]) if row else None
    except Exception as exc:
        logger.error("[sso] JIT provisioning failed: %s", exc)
        return None


def scim_provision_user(
    *,
    tenant: dict[str, Any],
    email: str,
    external_id: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> str | None:
    """SCIM-side user upsert that is INDEPENDENT of ``jit_provisioning``.

    SCIM is the IdP-driven lifecycle channel — when a tenant runs SCIM,
    they expect ``POST /Users`` to create the account regardless of
    whether JIT-on-first-login is enabled. (JIT governs login-time
    auto-create only; SCIM governs explicit pre-provisioning.) We key
    by (tenant_id, lowercased email) so a re-POST is idempotent. The
    SCIM-supplied ``external_id`` is persisted as ``sso_subject`` so a
    later SSO login matches the same row.
    """
    if not tenant or not email:
        return None
    email_norm = email.strip().lower()
    if not email_norm:
        return None
    subject = (external_id or email_norm).strip()

    # Residency gate (Task #12). SCIM provisions the user row, which
    # carries data_region; refuse on a process serving a different region.
    tenant_region = tenant.get("data_region")
    if tenant_region:
        from app.security.data_residency import (
            RegionMismatchError,
            assert_region_match,
        )

        try:
            assert_region_match(tenant_region, context="scim.provision_user")
        except RegionMismatchError:
            logger.error(
                "[scim] provisioning blocked by data residency for tenant=%s",
                tenant.get("tenant_id"),
            )
            return None

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Match by sso_subject within tenant first, then by email
                # within tenant — covers both pre-existing SSO users and
                # plain accounts being claimed by SCIM.
                cur.execute(
                    """
                    SELECT user_id FROM users
                    WHERE sso_tenant_id = %s
                      AND (sso_subject = %s OR LOWER(email) = %s)
                    LIMIT 1
                    """,
                    (tenant["tenant_id"], subject, email_norm),
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        """
                        UPDATE users SET
                            email = %s,
                            first_name = COALESCE(%s, first_name),
                            last_name = COALESCE(%s, last_name),
                            sso_subject = %s,
                            disabled_at = NULL,
                            disabled_reason = NULL
                        WHERE user_id = %s
                        """,
                        (email_norm, first_name, last_name, subject, existing["user_id"]),
                    )
                    conn.commit()
                    return str(existing["user_id"])
                cur.execute(
                    """
                    INSERT INTO users (
                        email, first_name, last_name, auth_provider,
                        sso_tenant_id, sso_subject,
                        mfa_required, created_at
                    )
                    VALUES (%s, %s, %s, 'scim', %s, %s, %s, NOW())
                    RETURNING user_id
                    """,
                    (
                        email_norm,
                        first_name,
                        last_name,
                        tenant["tenant_id"],
                        subject,
                        bool(tenant.get("require_mfa", True)),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return str(row["user_id"]) if row else None
    except Exception as exc:
        logger.error("[scim] provisioning failed: %s", exc)
        return None


def saml_enabled() -> bool:
    return os.getenv("ENABLE_SAML_SSO", "").strip().lower() in {"1", "true", "yes"}


def issue_scim_token() -> str:
    """Generate a fresh SCIM bearer token (caller stores the hash)."""
    return f"scim_{secrets.token_urlsafe(40)}"
