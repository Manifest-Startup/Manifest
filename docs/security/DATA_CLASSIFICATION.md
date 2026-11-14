# Data Classification Inventory

_Last reviewed: 2026-04-19 (Task #12)._

This document inventories every column that holds sensitive data, classifies it
against our four-tier taxonomy, and records the protection mechanism in force
today. It is the source of truth that auditors (SOC 2, ISO 27001, HIPAA) and
the engineering team consult before any new schema lands.

## Classification tiers

| Tier | Examples | Required protection |
|------|----------|---------------------|
| **C4 — Restricted** | OAuth bearer tokens, MFA secrets, SSO client secrets, encryption keys | At-rest field-level encryption (envelope, AES-256-GCM, per-tenant DEK), in-transit TLS 1.2+, redacted in logs, no exports |
| **C3 — Confidential PII/PHI** | Full name, email, customer company, survey free-text answers, IP addresses, request payloads | At-rest disk encryption + RLS + DSAR-deletable; field-level encryption recommended for free-text and PHI |
| **C2 — Internal** | Audit events, anonymous usage metrics, session metadata | Disk encryption + RLS, retention windows enforced |
| **C1 — Public** | Marketing copy, public idea titles after explicit publish | None required |

## Inventory

| Table.Column | Tier | Owner | At-rest protection | Notes |
|--------------|------|-------|--------------------|-------|
| `users.email`                                | C3 | Identity | TLS + RLS; tombstoned on purge | DSAR-deletable |
| `users.password_hash`                        | C4 | Identity | bcrypt | Never logged, never returned in API |
| `users.sso_subject`                          | C3 | Identity | RLS | Identifier; not a credential |
| `users.guest_merge_secret`                   | C4 | Identity | One-time, hashed | Rotated on merge |
| `password_history.password_hash`             | C4 | Identity | bcrypt | Limit 10 rows per user |
| `password_reset_tokens.token_hash`           | C4 | Identity | SHA-256 of high-entropy token | Raw token never persisted |
| `user_totp_mfa.secret_ciphertext`            | C4 | Identity | `pgp_sym_encrypt` w/ `MFA_ENCRYPTION_KEY` | Encrypted prior to Task #12 |
| `user_totp_mfa.recovery_codes`               | C4 | Identity | SHA-256 hashed | One-time use |
| `webauthn_credentials.public_key`            | C3 | Identity | RLS | Public key, but binds to user |
| `integrations.access_token`                  | C4 | Integrations | **Envelope (Task #12)** — `access_token_ciphertext`, per-user DEK | Plaintext column kept until cutover; gated by `ENCRYPT_INTEGRATIONS_TOKENS` |
| `integrations.refresh_token`                 | C4 | Integrations | **Envelope (Task #12)** — `refresh_token_ciphertext`, per-user DEK | Same |
| `sso_tenant_configs.oidc_client_secret_encrypted` | C4 | Identity | `pgp_sym_encrypt` | Tenant-isolated |
| `sso_tenant_configs.scim_token_hash`         | C4 | Identity | SHA-256 hash | Bearer token never persisted in clear |
| `api_keys.key_hash`                          | C4 | API | bcrypt (Task #11) | SHA-256 legacy supported until rotation |
| `api_keys.last_used_ip`                      | C2 | API | INET | Forensic only |
| `customers.full_name`                        | C3 | CRM | Disk encryption + RLS | Roadmap: field encrypt under per-tenant DEK |
| `customers.company`                          | C3 | CRM | Disk encryption + RLS | Same |
| `customers.metadata`                         | C3 | CRM | Disk encryption | Free-text — review for PHI |
| `survey_responses.contact_email`             | C3 | Research | Disk encryption | DSAR-deletable |
| `survey_responses.answers` (JSONB)           | C3 | Research | Disk encryption | May contain free-form PHI; review per study |
| `privacy_consents.ip_hash`                   | C2 | Privacy | SHA-256 + salt | Already hashed at write |
| `privacy_consents.consent_payload`           | C2 | Privacy | RLS | No PII inside payload |
| `admin_audit_events.metadata`                | C2 | Audit | Append-only | No raw secrets ever logged here |
| `admin_audit_events.request_ip`              | C2 | Audit | INET | Retain per `DATA_RETENTION.md` |
| `tenant_data_keys.wrapped_dek` (Task #12)    | C4 | Crypto | KEK-wrapped (AES-GCM) | Deletion = crypto-shred |

## Cross-cutting controls

- **At-rest** — Postgres data files are encrypted at the storage layer
  (Replit-managed). Field-level encryption layered on top for C4 columns.
- **In-transit** — TLS 1.2+ for all external connections; mTLS for the
  Replit ↔ user proxy.
- **Logs** — `app.utils.logger` redacts known secret patterns (Task #14
  hardens this). KEKs and DEKs are NEVER passed to `logger`.
- **Backups** — See `BACKUP_AND_RESTORE.md`. Backups inherit the encryption
  envelope so restoring without the active KEK still produces unreadable
  ciphertext.

## Change control

Adding a new column that holds C3 or C4 data requires:
1. An entry in this table BEFORE the migration is merged.
2. If C4: field-level encryption via `app.security.crypto.encrypt_field` and
   a per-tenant DEK from `app.security.tenant_keys.get_or_create_tenant_dek`.
3. Inclusion in `app.services.tenant_purge_service.USER_DATA_PURGE_PLAN`
   when the data is per-user.
