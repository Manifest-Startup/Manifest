# HIPAA Program (Business Associate)

Manifest acts as a *Business Associate* under 45 CFR §160.103 when a
covered-entity customer signs a BAA. This document is the program
overview; see linked policies for detail.

## 1. Officers

| Role | Owner |
|---|---|
| Privacy Officer (45 CFR §164.530(a)) | DPO — dpo@manifest.example |
| Security Officer (45 CFR §164.308(a)(2)) | CISO — security@manifest.example |

## 2. BAA

A signed BAA is required *before* PHI is processed. The current
template lives at `docs/legal/BAA_TEMPLATE.md`. Customer-redlined BAAs are
stored in the contracts vault under `legal/baa/`.

## 3. Administrative safeguards (§164.308)

- **Risk analysis** — DPIA (`docs/privacy/DPIA.md`) refreshed yearly.
- **Workforce training** — annual HIPAA + security awareness training.
  Training log: `docs/security/TRAINING_LOG.md` (one row per employee +
  completion date).
- **Workforce clearance** — background checks pre-hire; access reviews
  quarterly per `docs/security/ACCESS_REVIEW.md` (T11).
- **Sanction policy** — documented in the employee handbook.
- **Information access management** — least-privilege roles enforced
  via permissions service (T11), reviewed quarterly.
- **Contingency plan** — backup + DR + tested recovery
  (`docs/security/BACKUP_AND_RESTORE.md`, supplemented by the
  incident-response runbook `docs/security/INCIDENT_RESPONSE_RUNBOOK.md`).
- **Periodic evaluation** — annual HIPAA-program review by the DPO.

## 4. Physical safeguards (§164.310)

Inherited from sub-processors (Replit, Supabase) — see
`docs/privacy/SUB_PROCESSORS.md`. Manifest has no on-prem PHI storage.

## 5. Technical safeguards (§164.312)

| Requirement | Implementation |
|---|---|
| Access control (a) | Per-tenant DEK + RBAC + step-up re-auth (T11/T12) |
| Audit controls (b) | Hash-chained, fail-closed audit log (T14) |
| Integrity (c) | DB checksums + audit chain prevents tampering |
| Person/entity authentication (d) | Password + MFA (TOTP/WebAuthn) |
| Transmission security (e) | TLS 1.2+ everywhere; HSTS preload |

## 6. Minimum-necessary standard

Engineering and support workflows are scoped via permissions so staff
only see PHI required for the task. The "min-necessary" review is part
of every code review for PHI-touching code paths.

## 7. Breach notification (§164.404-410)

See `docs/privacy/BREACH_NOTIFICATION.md`. HIPAA-specific timers
(60 days to individuals, HHS) are tracked alongside GDPR clocks.

## 8. Subcontractors

Every sub-processor that touches PHI must execute a BAA back-to-back
with Manifest before being onboarded. Tracked in
`docs/privacy/SUB_PROCESSORS.md`.

## 9. Documentation retention

All HIPAA documentation (policies, training records, risk analyses,
breach register) is retained for **6 years** from the date of creation
or the date last in effect, whichever is later (45 CFR §164.530(j)).
