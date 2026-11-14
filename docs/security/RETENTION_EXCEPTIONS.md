# Data Retention Exception Register

Owner: DPO + Security Officer. Cadence: reviewed quarterly + on every
add/remove. Pairs with `docs/security/DATA_RETENTION.md`.

## Purpose

The default retention policy is enforced nightly by
`backend/scripts/run_privacy_retention.py`. Any record that should be
preserved *beyond* the default schedule (live litigation hold, regulator
investigation, signed contractual obligation, in-flight breach
investigation, etc.) **must** be enumerated here. Anything not in this
register is in scope for automatic deletion / minimisation.

## Schema

Each entry is a YAML stanza in `backend/config/retention_exceptions.yaml`.
The orchestrator loads the file at start-up and skips matching rows.

```yaml
- id: LIT-2026-001                # stable, opaque
  scope: "users"                  # logical table or data class
  match: "user_id IN ('...')"     # SQL fragment, parameter-free
  reason: "Active litigation hold — Smith v. Manifest"
  approved_by: "DPO"
  opened_at: "2026-04-01T00:00:00Z"
  expected_close: "2026-12-31"
  ticket: "LEGAL-218"
```

## Process

1. **Open** — Legal/Security raises a ticket, DPO reviews proportionality,
   adds an entry to the YAML register *and* commits the change.
2. **Apply** — Deploy or restart the retention job; entry takes effect at
   next run. The job emits a `retention_exception_applied` audit event
   per matching scope so the postponement is provable.
3. **Review** — Quarterly the DPO + Security Officer scan every open
   entry: still justified? still narrowest scope? Update or close.
4. **Close** — Remove the YAML entry and let the next nightly run perform
   the deferred deletions. A `retention_exception_closed` audit event is
   recorded.

## Operational endpoint

`GET /api/dsar/retention/exceptions` (admin scope, AUTH-tier rate limit)
returns the active register so the trust-center page and external
auditors can verify what is currently being held back and why. The
endpoint never reveals the SQL `match` predicate (which may itself
contain identifiers); it returns scope, reason, opened/closed dates,
and approver only.

## Audit / SOC 2 mapping

- SOC 2 CC6.5 / CC7.1 — provable deviation from default retention with
  approver + reason.
- ISO 27001 A.5.34 — privacy and PII protection.
- GDPR Art. 5(1)(e) — storage limitation; documented exceptions.
