# Encryption & Key Management

_Last reviewed: 2026-04-19 (Task #12)._

## Overview

Manifest implements industry-standard envelope encryption for all
**Restricted (C4)** data at rest:

```
plaintext --(DEK, AES-256-GCM)--> ciphertext_field
DEK -------(KEK, AES-256-GCM)--> wrapped_dek (in tenant_data_keys)
```

The KEK is supplied via environment variables and is the only cryptographic
secret outside the database. The DEK is per-tenant, persisted in
`tenant_data_keys` wrapped under the active KEK, and unwrapped lazily into
the application worker's process memory.

Implementation: `backend/app/security/crypto.py` and
`backend/app/security/tenant_keys.py`.

## Algorithms

| Concern | Algorithm | Notes |
|---------|-----------|-------|
| Symmetric encryption | AES-256-GCM (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`) | 256-bit keys, 96-bit random nonce, 128-bit tag |
| Random nonce | `os.urandom(12)` | Per-row, never reused |
| Password hashing | bcrypt (cost 12) | `app.security.passwords` |
| API key hashing | bcrypt (after SHA-256 normalisation, see `api_key_service`) | SHA-256 fallback for legacy rows |
| Reset token hashing | SHA-256 of high-entropy token | `app.services.identity.reset_tokens` |
| TOTP secret | `pgp_sym_encrypt` w/ `MFA_ENCRYPTION_KEY` | Pre-existing, see `totp_mfa_service` |

We deliberately use **AES-GCM, not GCM-SIV**: nonces are random and never
reused (tracked by the nonce-per-row contract above). If we need
deterministic / searchable encryption in the future (e.g. for `users.email`
exact match), we will introduce HMAC-SHA-256 blind-index columns rather than
weakening the GCM choice.

## KEK lifecycle

### Provisioning

KEKs are 32 random bytes, base64-encoded, and stored in the secrets manager
under the names `MANIFEST_KEK_V1`, `MANIFEST_KEK_V2`, ….

```
$ python -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())'
```

`MANIFEST_KEK_ACTIVE_VERSION` selects the version writers use. Multiple
versions may be configured at once so reads of older ciphertexts continue
to succeed during rotation.

### Rotation runbook

KEK rotation is a quarterly cadence (HIPAA / SOC 2 CC6.1).

1. Generate a new KEK and load it as `MANIFEST_KEK_V<n+1>`.
2. **Do not** flip the active version yet. Roll out the env var to every
   worker (deployment release).
3. Flip `MANIFEST_KEK_ACTIVE_VERSION` to `n+1`. New writes immediately use
   the new KEK to wrap fresh DEKs.
4. Run the DEK-rewrap job: for each row in `tenant_data_keys` where
   `kek_version != active`, unwrap with the old KEK and rewrap with the
   new one. The on-disk ciphertext (the field-level blob) does NOT need to
   be re-encrypted because the DEK is unchanged — only its wrapper.
5. Once `tenant_data_keys.kek_version` is uniformly `n+1`, retire the old
   KEK env var on the next deploy.

### Compromise response

If a KEK is suspected compromised:

1. Flip `MANIFEST_KEK_ACTIVE_VERSION` to a freshly-generated version.
2. **Re-key every DEK**: for each tenant, `unwrap_dek` with the suspect
   KEK in memory, then `wrap_dek` immediately under the new active KEK.
   Persist the new wrapped DEK and DELETE the old wrapped DEK row.
3. Force-rotate every C4 secret that was decryptable under the suspect
   KEK (OAuth tokens via the third-party provider, MFA seeds via user
   re-enrolment).

## DEK lifecycle

DEKs are generated lazily on first write per `(tenant_kind, tenant_id)`
pair. There is exactly one active DEK row per tenant at a time — the
`UNIQUE (tenant_kind, tenant_id, kek_version)` constraint plus the
`revoked_at IS NULL` partial index enforce this.

DEKs are **never logged** and **never returned in API responses**. They
live in the application worker's process memory only after being unwrapped
by the active KEK; restart of the worker drops the cache and forces a
fresh unwrap (which still requires the KEK).

## Crypto-shred (right to erasure)

`app.security.tenant_keys.purge_tenant_keys(tenant_kind, tenant_id)`
deletes every wrapped DEK row for a tenant. Once the wrapped DEK is gone,
every ciphertext encrypted under that DEK is permanently undecryptable —
even an attacker holding both the database backups and the active KEK
cannot read the data.

This is the primary mechanism behind
`app.services.compliance.tenant_purge.purge_user_data` (the GDPR Art. 17 /
CCPA §1798.105 endpoint). The plaintext rows are also deleted/tombstoned
in the same transaction as defence-in-depth.

## Field-level encryption — current coverage

| Table.Column | Status | Feature flag |
|--------------|--------|--------------|
| `integrations.access_token`  | Available, OFF by default | `ENCRYPT_INTEGRATIONS_TOKENS=1` |
| `integrations.refresh_token` | Available, OFF by default | `ENCRYPT_INTEGRATIONS_TOKENS=1` |
| `user_totp_mfa.secret_ciphertext` | Always on (legacy `pgp_sym_encrypt`) | n/a |
| `sso_tenant_configs.oidc_client_secret_encrypted` | Always on (legacy `pgp_sym_encrypt`) | n/a |

### Online cutover for `integrations`

1. Apply migration `setup_data_protection_tables.py` (adds nullable
   ciphertext columns + key version metadata; no behaviour change).
2. Deploy app code that reads from ciphertext-when-present (already
   merged in Task #12). Reads of legacy plaintext rows continue to work.
3. Flip `ENCRYPT_INTEGRATIONS_TOKENS=1`. New writes encrypt; reads still
   transparent.
4. Run `backfill_encrypted_tokens()` — encrypts old plaintext rows in
   batches of 100 with `FOR UPDATE SKIP LOCKED` so it can run online.
5. After verifying every row has `access_token IS NULL` and
   `access_token_ciphertext IS NOT NULL`, drop the legacy plaintext
   columns in a follow-up migration.

Reverting the flag at any point is safe: writes go back to plaintext but
ciphertext rows continue to be readable.

## Test coverage

- `backend/tests/test_security/test_crypto.py` — KEK wrap/unwrap round-trip,
  field encrypt/decrypt round-trip, AAD mismatch fail-closed, fail-closed
  on corrupted blob, KEK version mismatch behaviour.
- `backend/tests/test_security/test_data_residency.py` — `assert_region_match`
  raises on mismatch, `current_region` env override, normalisation.
