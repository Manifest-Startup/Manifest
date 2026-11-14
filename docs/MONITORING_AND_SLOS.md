# Monitoring, Detection & Service-Level Objectives

> Companion to `docs/AUDIT_LOGGING.md`. SOC 2 CC7.2 / ISO 27001 A.8.16
> require that we *operationalize* the security telemetry — not just
> collect it. This document is the contract between Engineering and
> the on-call rotation.

## 1. Critical SLOs

| Surface                       | Objective | Window | Pager |
|-------------------------------|-----------|--------|-------|
| Audit-event ingestion lag     | p99 < 5 s end-to-end (emit → SIEM JSONL) | 30 d  | Sec on-call |
| Audit hash-chain verifier     | runs nightly, alerts on first mismatch    | daily | Sec on-call |
| Brute-force detector fire-time| < 60 s after the threshold-crossing event | 30 d  | Sec on-call |
| Privilege-escalation detector | < 30 s after a `role_changed→admin`       | 30 d  | Sec on-call |
| Retention worker              | runs daily; ≥99 % completion rate         | 30 d  | Platform on-call |

A breach of any SLO opens a Sev-2 in the IR runbook
(`docs/INCIDENT_RESPONSE.md`).

## 2. Detectors → alerts

Each `detection_*` event written to `security_audit_events` is
forwarded to the SIEM JSONL sink (`AUDIT_SINK_PATH`) where the
following routes apply:

| Event type                          | Severity | Route          |
|-------------------------------------|----------|----------------|
| `detection_brute_force`             | HIGH     | PagerDuty `sec-primary` |
| `detection_impossible_travel`       | HIGH     | PagerDuty `sec-primary` |
| `detection_priv_escalation`         | HIGH     | PagerDuty `sec-primary` |
| `detection_audit_chain_break`       | CRITICAL | PagerDuty `sec-primary` + #sec-incident |
| `detection_mfa_bypass_attempt`      | HIGH     | PagerDuty `sec-primary` |
| `detection_secret_scan_hit`         | HIGH     | #sec-triage |
| `detection_dependency_vulnerability`| HIGH     | #sec-triage |
| `detection_error_spike`             | HIGH     | #platform-oncall |
| `detection_abnormal_ai_usage`       | MEDIUM   | #abuse |
| `detection_mass_export`             | HIGH     | PagerDuty `sec-primary` |
| `audit_retention_purge`             | MEDIUM   | #audit-log (info) |

## 3. Status page & external comms

Customer-visible incidents are published to the public status page
within 30 minutes of declaration. The page link is referenced in
`SECURITY.md`.

## 4. Tuning knobs

All thresholds are env-configurable:

```
AUDIT_BRUTE_FORCE_THRESHOLD       (default 5)
AUDIT_BRUTE_FORCE_WINDOW_S        (default 600)
AUDIT_IMPOSSIBLE_TRAVEL_WINDOW_S  (default 3600)
AUDIT_MASS_EXPORT_THRESHOLD       (default 25)
AUDIT_MASS_EXPORT_WINDOW_S        (default 300)
AUDIT_RETENTION_DAYS              (default 365, HIPAA = 2190)
AUDIT_SINK_ENABLED                (default 1)
AUDIT_SINK_PATH                   (default /var/log/manifest/audit.jsonl)
AUDIT_SINK_INCLUDE_METADATA       (default 0 — opt-in for SECRET/ADMIN)
```

## 5. Verification cadence

* **Nightly:** `python -m backend.scripts.verify_audit_chain` (or the
  equivalent cron entry) — alerts on the first hash mismatch.
* **Nightly:** `python -m backend.scripts.run_audit_retention` —
  enforces the retention floor and emits the `audit_retention_purge`
  marker.
* **Weekly:** on-call sweep of the SIEM dashboard for unexplained
  detection volume changes (>2σ from rolling 30-day baseline).
* **Quarterly:** tabletop incident exercise covering at least one
  HIGH detector path end-to-end.
