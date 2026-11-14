# Manifest SOC 2 Readiness

This document translates the application hardening work in the codebase into the operational controls needed for a professional SaaS security program.

## Control owners

- Engineering: application security, dependency patching, CI gates, session/MFA controls, audit logging.
- Product: privacy UX, deletion/export flows, customer-facing disclosures.
- Operations: incident response, backups, recovery drills, security monitoring.
- Leadership: access reviews, vendor approvals, policy signoff, auditor engagement.

## Recurring operating cadence

### Weekly

- Review Dependabot pull requests and merge security updates.
- Review failed `dependency-audits` CI runs in GitHub Actions.
- Review security audit events for MFA changes, password resets, API key lifecycle, and session revocations.

### Monthly

- Run an access review for production systems, GitHub admins, Supabase roles, and deployment credentials.
- Review open vendor risks and confirm DPAs remain current for AI, analytics, email, and infrastructure providers.
- Sample deletion/export requests and verify they completed within the expected support SLA.

### Quarterly

- Execute an incident-response tabletop exercise and record outcomes.
- Review retention windows, privacy disclosures, and cookie/analytics behavior against production reality, including the `privacy_consents` audit trail and the `/api/privacy/consent` browser flow.
- Review authentication posture: MFA adoption, stale sessions, password reset rate-limit metrics, and API key inventory.

## Access review checklist

- Enumerate all users with production access.
- Confirm least-privilege role for each person.
- Remove former employees or inactive contractors.
- Confirm service accounts are documented, rotated, and scoped.
- Record reviewer, date, systems reviewed, and remediation actions.

## Vendor review checklist

- Vendor name and business purpose.
- Data types shared with the vendor.
- DPA / privacy terms on file.
- Security review completed (SOC 2, ISO 27001, or equivalent).
- Breach notification commitment documented.
- Owner assigned for renewals and risk decisions.

## Incident response minimums

- Severity matrix with customer-impact criteria.
- Named incident commander and communications lead.
- Log preservation procedure.
- Customer notification decision tree.
- Post-incident review template with root cause and corrective actions.

See also: `docs/security/INCIDENT_RESPONSE_RUNBOOK.md`.

## Auditor evidence to preserve

- Architecture and data-flow diagrams.
- Screenshots or exports of MFA/session controls in the account UI.
- Screenshots or exports of the privacy banner and account privacy controls, plus sample `privacy_consents` rows.
- Examples of security audit events from the `security_audit_events` table.
- GitHub branch protection, CI policy, and dependency audit history.
- Access review records and vendor review records.
- Incident drill notes and follow-up actions.

## External audit preparation

- Choose Trust Services Criteria scope: at minimum `Security`, optionally `Availability`, `Confidentiality`, and `Privacy`.
- Decide on SOC 2 Type I vs Type II timeline.
- Export a control matrix mapping app controls, owners, evidence, and review frequency.
- Engage a CPA firm only after at least one full control cycle is operating consistently.
