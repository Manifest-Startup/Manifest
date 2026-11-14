# Backup Integrity & Restore Drill

_Last reviewed: 2026-04-19 (Task #12)._

## Backup posture

- **Provider** — Replit-managed Postgres. Daily full snapshots + 5-min PITR.
- **Encryption** — Backups inherit storage-layer AES-256 encryption. C4
  columns are additionally protected by envelope encryption
  (`ENCRYPTION_AND_KEY_MANAGEMENT.md`), so a leaked backup without the
  active KEK is unreadable for those columns.
- **Retention** — 30 days of daily snapshots, 7 days of PITR, 365 days of
  monthly archival snapshots (encrypted with a separate "archival KEK").
- **Geographic redundancy** — Backups are replicated to a second region in
  the same legal jurisdiction. Cross-jurisdiction replication only happens
  for tenants whose `data_region` permits it (see `DATA_RESIDENCY.md`).

## Integrity verification

Every backup is checksummed (SHA-256) at rest. The
`backup_integrity_checks` table records each successful verification with
`backup_id`, `sha256`, `size_bytes`, `verified_at`, `verified_by`, and
optional `restore_drill_run_id`.

A verification job runs nightly:

```
python -m backend.scripts.verify_backups        # planned for Task #14
```

For now, verification is recorded manually after the SRE confirms the
checksum reported by the provider matches the value stored in
`backup_integrity_checks`.

## Restore drill cadence

- **Weekly** — Provider's automated PITR test to a throwaway database.
  Pass/fail emitted to monitoring.
- **Quarterly** — Full restore drill into an isolated environment
  performed by the on-call SRE. Drill steps:
  1. Provision a clean Postgres instance in the same region.
  2. Restore the most recent daily snapshot.
  3. Apply WAL logs to a chosen RPO target (≤ 5 minutes).
  4. Run the application's smoke test suite against the restored DB.
  5. Insert a row into `backup_integrity_checks` with the
     `restore_drill_run_id` and a short note (RTO observed, RPO observed,
     anomalies).
- **Annual** — Full DR exercise that spins up the application stack
  against the restored DB and runs end-to-end tests.

### RTO / RPO commitments

| Scenario | RTO | RPO |
|----------|-----|-----|
| Single-table corruption | 30 minutes | ≤ 5 minutes |
| Database loss, same region | 2 hours | ≤ 5 minutes |
| Region-wide outage | 8 hours | ≤ 1 hour |

## Crypto considerations during restore

Because field-level encryption depends on the KEK environment variables,
restoring a backup without first provisioning the matching `MANIFEST_KEK_V*`
values will leave C4 columns unreadable. The runbook step for restore is:

1. Provision Postgres.
2. Restore data.
3. Provision the secrets manager and load the same `MANIFEST_KEK_V*` values
   that were active when the backup was taken (the KEK version of every
   wrapped DEK is recorded in `tenant_data_keys.kek_version`).
4. Bring the application up. `tenant_keys.get_or_create_tenant_dek`
   transparently uses the restored KEKs.

If a KEK has been rotated since the backup was taken, both the old and new
KEKs must be present so the DEK rewrap step can run before the old KEK is
retired.
