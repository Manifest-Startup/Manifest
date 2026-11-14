# Data Retention and Privacy Controls

Owner: DPO + Engineering. Last reviewed: 2026-04-19.

## 1. Retention schedule

Enforced nightly by `backend/scripts/run_privacy_retention.py`. Each
class is overridable via the listed environment variable.

| Data class | Retention | Mechanism | Override |
|---|---|---|---|
| Password reset tokens | 24 hours after expiry | DELETE expired rows | `MANIFEST_RETENTION_PWRESET_DAYS` |
| Idle user sessions | 90 days since last seen | DELETE | `MANIFEST_RETENTION_SESSIONS_DAYS` |
| Guest accounts (un-converted) | 30 days | DELETE | `MANIFEST_RETENTION_GUEST_DAYS` |
| Anonymous consent ledger rows | 5 years | DELETE rows with no user_id and no visitor_id | `MANIFEST_RETENTION_CONSENT_DAYS` |
| Authenticated consent ledger | Account lifetime + 30 days post-deletion | Tied to crypto-shred on erasure | n/a |
| Hot audit log | 1 year | Cold-tier archive after 1y; see audit retention runner | `AUDIT_RETENTION_*` (T14) |
| Cold audit archive | 7 years | Encrypted offline storage | n/a |
| Backups | 35 days | Snapshot rotation at Supabase | n/a |
| Customer support tickets | 2 years from last interaction | Manual purge | n/a |
| Marketing email lists | Until withdrawal | Consent ledger | n/a |
| Tax / billing records | 7 years | Stripe + finance archive | n/a |

## 2. Right-to-erasure

A user request via `POST /api/dsar/erase` triggers
`tenant_purge_service.purge_tenant`. In a single DB transaction:
1. The wrapped tenant DEK is deleted (`tenant_data_keys`) — every
   ciphertext encrypted under that DEK becomes unrecoverable.
2. Leaf PII rows are deleted in the order defined by
   `USER_DATA_PURGE_PLAN`.
3. The user row is tombstoned (email replaced, password nulled).
4. An admin audit event is emitted with per-table delete counts.

The DSAR endpoint returns a tamper-evident **deletion certificate**
containing the certificate id, completion timestamp, SHA-256 of the
counts summary, audit event id, and the per-table counts. The same
fields are persisted to the chained security audit log.

## 3. Operational controls

- The retention runner is scheduled to run nightly (cron / k8s
  CronJob / Replit scheduled deployment).
- Failures are surfaced via a non-zero exit code and a SIEM alert
  through the audit log (`retention_run_completed` with `outcome=partial`).
- Quarterly privacy review verifies: schedule alignment with policy,
  override env values, and that the runner has actually executed.

## 4. Backups & DR

Daily encrypted snapshots are taken by the managed DB provider with
35-day retention. Backups are encrypted at rest with the provider's
KMS and are not exempt from the right-to-erasure: when a deletion
request is fulfilled the corresponding DEK is purged, so any backup
restoration cannot recover that user's encrypted plaintext.

## 5. Support workflow for ad-hoc requests

1. User exports their workspace data (`/api/dsar/portability`).
2. User submits an erasure request (`/api/dsar/erase`) confirming
   their email and acknowledging irreversibility.
3. The DSAR audit event records the deletion certificate.
4. Support verifies the certificate id with the user and follows up
   in any downstream system that holds mirrored data (e.g. Stripe).
5. Engineering reviews the quarterly privacy report for any class
   that did not converge.
