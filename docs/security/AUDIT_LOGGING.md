# Manifest Audit Logging Architecture

This document describes how Manifest records, protects, and ships
security-relevant events. It is the design reference for SOC 2 CC7.2
("Anomalies in the system are detected"), CC7.3 ("Communicates relevant
information"), and the audit-trail expectations in HIPAA §164.312(b)
and ISO 27001 A.12.4.

## Components

| Component | Path | Responsibility |
|-----------|------|----------------|
| Canonical schema + hash chain | `backend/app/security/audit_chain.py` | Defines event registry (type, category, severity, sensitivity), redacts metadata, computes the per-row hash chain. |
| Writer | `backend/app/services/security_audit_service.py` | The single allowed insertion point. Sanitises, links into the chain under an advisory lock, mirrors to the SIEM stream. |
| SIEM sink | `backend/app/security/audit_sink.py` | Append-only JSONL stream under `AUDIT_SINK_PATH`. Daily rotation. Off-host preservation target. |
| Verifier | `backend/app/security/audit_verifier.py` | Re-hashes stored rows in order and reports any break. |
| Detections | `backend/app/security/audit_detections.py` | Brute-force, impossible-travel, mass-export, privilege-escalation heuristics that emit tagged `detection_*` events. |
| Migration | `backend/scripts/setup_audit_chain_tables.py` | Idempotent DDL — runs at app startup. |
| Retention worker | `backend/app/security/audit_retention.py` + `backend/scripts/run_audit_retention.py` | Daily purge with a 1-year floor (SOC 2 / ISO 27001). HIPAA tenants set `AUDIT_RETENTION_DAYS=2190` (6 years). Marker-first DELETE: the worker emits an `audit_retention_purge` event before removing rows, then deletes only `created_at < cutoff AND (seq IS NULL OR seq < marker_seq)` so the marker (and anything newer) is provably untouchable while legacy pre-chain rows are still purged. |
| Fail-closed writer | `backend/app/services/security_audit_service.py` | If a chained INSERT fails, we refuse to write a non-chained legacy row by default and emit a `detection_audit_chain_break` to the SIEM sink. Operators may set `AUDIT_ALLOW_LEGACY_FALLBACK=1` *only* during a forward migration; the fallback path logs a degraded-mode warning. |
| Chain-break alerting | `backend/app/security/audit_verifier._alert_on_break` | Every `verify_chain` / `verify_chain_window` run that reports `is_intact=False` emits a `detection_audit_chain_break` (severity=critical) so on-call sees the integrity loss within hours, not quarters. |
| PII redaction at writer boundary | `backend/app/services/security_audit_service.py` | Top-level canonical identity fields (`actor_id`, `target_id`, `tenant_id`) are passed through a pseudonymizer before persistence. Email-shaped values are replaced with a stable `email:<sha256-prefix>` token so cross-row correlation still works for IR while raw PII never lands in the immutable audit table or the SIEM stream. Non-email identifiers (UUIDs, slugs) pass through unchanged. |

## Schema

`security_audit_events` columns relevant to the chain:

| Column | Purpose |
|--------|---------|
| `seq` (BIGSERIAL) | Monotonic insertion order. Used by the verifier to walk the chain deterministically. |
| `event_id` (UUID PK) | Stable identifier for the event row. |
| `event_type` (TEXT) | The registered event-type string (e.g. `login_success`). |
| `category` (TEXT) | Mirror of `EventDefinition.category`. Drives SIEM routing. |
| `severity` (TEXT) | Mirror of `EventDefinition.severity`. Drives paging. |
| `sensitivity` (TEXT) | Mirror of `EventDefinition.sensitivity`. The SIEM sink drops the metadata payload for `secret`. |
| `user_id`, `request_ip`, `session_id`, `request_id` | Correlation fields. |
| `actor_id`, `actor_type` | Who initiated (user / service / system / anonymous). |
| `action`, `target_type`, `target_id` | Canonical "who-did-what-to-what" triple required by SOC 2 CC7.2 / ISO 27001 A.8.15. |
| `tenant_id` | Multi-tenant correlation key. |
| `user_agent` | Client UA (truncated to 500 chars). |
| `outcome` | `success` / `failed` / `denied` / `rejected` / `rate_limited`. |
| `metadata` (JSONB) | Sanitised JSON payload. Always passes through `sanitize_metadata` first. |
| `prev_hash` | The previous row's `event_hash`, or 64 zero hex chars for the genesis row. |
| `event_hash` | `sha256(prev_hash || ":" || canonical_payload)`. UNIQUE. |
| `created_at` | Server timestamp included in the canonical payload. |

## Hash chain guarantees

The chain is **tamper-evident, not tamper-proof**. The properties it
gives us:

- Any UPDATE to a historical row changes that row's expected hash, so
  every later row's `prev_hash` no longer matches and `verify_chain`
  surfaces the break.
- A DELETE of any row leaves the next row's `prev_hash` pointing at a
  hash that no longer exists, also caught by the verifier.
- A re-ordering attack (swap two rows) breaks the chain at both swap
  points.
- A duplicate insert is blocked by the `UNIQUE(event_hash)` index.

The chain does **not** prevent an attacker with full DB superuser
access from rewriting history *and* recomputing every subsequent
hash. That is what the SIEM JSONL stream defends against — once a
record is written to the off-host store, the attacker would also need
to compromise that store to hide the gap.

## Sanitisation

Every emit runs metadata through `sanitize_metadata`, which:

1. Deep-copies the dict so the caller's object is never mutated.
2. Walks every nested string and applies the redactors in
   `app.security.ai_safety.redact_for_logs` (OpenAI keys, Stripe keys,
   AWS / GitHub / Slack tokens, JWTs, private keys, SSNs, credit cards,
   email addresses).
3. Truncates any single string to 2 000 characters so a runaway prompt
   cannot blow up a single row.

Callers are still expected to pass *minimal* metadata. The redactor is
the last line of defence, not the first.

## SIEM stream

Format: line-delimited JSON, one event per line, daily rotation.
Configuration:

| Env var | Default | Purpose |
|---------|---------|---------|
| `AUDIT_SINK_ENABLED` | unset (disabled) | Truthy values (`1`, `true`, `yes`, `on`) enable the sink. Disabled in tests and unconfigured dev. |
| `AUDIT_SINK_PATH` | `logs/audit/` | Directory the JSONL files land in. The operator's sync agent (S3, GCS, Splunk forwarder, …) reads from here. |
| `AUDIT_SINK_INCLUDE_METADATA` | unset (suppress high-risk) | When truthy, exports metadata for high-risk categories (admin/privacy/detection) and severity=critical events too. Leave **unset** unless your SIEM is in a tightly-controlled trust zone. |

Operational notes:

- The sink is **best-effort**. A sink failure is logged at WARNING and
  swallowed — the database row remains the source of truth.
- The export drops the metadata payload (`metadata_omitted: true`)
  by default for any of:
  - `Sensitivity.SECRET` events (always — not overridable);
  - high-risk categories (`admin`, `privacy`, `detection`);
  - `Severity.CRITICAL` events of any category.
  This is defence-in-depth on top of `sanitize_metadata`: even if a
  novel secret format slipped past the redactor, the off-host export
  carries only the chain coordinates. Operators who want full
  payloads in their SIEM can opt back in with
  `AUDIT_SINK_INCLUDE_METADATA=1` for the lower-risk classes.
- The sink writes to local disk first; off-host shipping is a
  separate operational concern (we do not ship from inside the app
  process so a network outage in the shipper doesn't back-pressure
  request handlers).

## Detections

`audit_detections` is intentionally a small set of cheap heuristics
that run inline next to the relevant emit site. Each detector is a
boolean function that, when tripped, records its own
`detection_*` event into the chain.

| Detector | Trip condition | Severity |
|----------|----------------|----------|
| `detect_brute_force` | ≥ `AUDIT_BRUTE_FORCE_THRESHOLD` (default 10) `login_failed` rows for one user_id OR one IP within `AUDIT_BRUTE_FORCE_WINDOW_S` (default 300 s) | high |
| `detect_impossible_travel` | A second `login_success` for the same user from a different coarse IP region within `AUDIT_IMPOSSIBLE_TRAVEL_WINDOW_S` (default 3 600 s) | high |
| `detect_mass_export` | ≥ `AUDIT_MASS_EXPORT_THRESHOLD` (default 50) export-class events for one user within `AUDIT_MASS_EXPORT_WINDOW_S` (default 600 s) | high |
| `detect_privilege_escalation` | Any role change targeting `admin` | high |

The IP region used by impossible-travel is a coarse `/16` (IPv4) or
`/48` (IPv6) prefix. Operators with a real GeoIP feed can override
`_ip_prefix` in a future iteration without changing the call sites.

## Verifier

`verify_chain` and `verify_chain_window` walk the rows in `seq` order,
recompute the expected `event_hash`, and compare against the stored
value. They return a `VerificationReport` with `(total_rows,
verified_rows, breaks)`. `quick_self_check()` is the cheap nightly
entry point — it covers the last 24 hours.

A break should be treated as a `critical`-severity incident until
proven to be a bug. The runbook escalates automatically because
`detection_audit_chain_break` is registered as `Severity.CRITICAL`.

## Operator runbook

| Task | How |
|------|-----|
| Verify the chain is intact for the last 24 h | `python -c "from app.security.audit_verifier import quick_self_check; print(quick_self_check())"` |
| Verify the entire chain | `python -c "from app.security.audit_verifier import verify_chain; print(verify_chain())"` |
| Tail the live SIEM stream (when enabled) | `tail -F $AUDIT_SINK_PATH/audit-$(date -u +%Y-%m-%d).jsonl` |
| List registered event types | `python -c "from app.security.audit_chain import all_definitions; [print(d.event_type, d.severity.value) for d in all_definitions()]"` |
