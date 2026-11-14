# Incident Response Tabletop — 2026 Q2

## Logistics

- **Date:** 2026-04-19
- **Format:** Synchronous walk-through of a hypothetical incident using
  the production runbook (`docs/security/INCIDENT_RESPONSE_RUNBOOK.md`).
- **Participants (roles, not individuals — fill in for each real drill):**
  - Incident Commander
  - Engineering on-call
  - Product / Customer Communications lead
  - Privacy / Compliance lead
  - Note-taker (records timeline, follow-ups, and verbatim decisions)
- **Out of scope:** No production changes are made. No real customer
  data is touched.

## Scenario

> At 14:02 UTC, the audit chain verification job
> (`audit_verifier.quick_self_check()`) fires
> `detection_audit_chain_break` (severity `critical`) covering the last
> 6 hours of `security_audit_events`. Five minutes earlier, the same
> user account exhibited:
> - one `login_success` from a new IPv4 region (Frankfurt /16),
> - immediately followed by `mfa_disabled`,
> - then `api_key_created` with the maximum scope set,
> - then `detection_mass_export` after 60+ generated PDFs in 5 minutes.
>
> The on-call engineer confirms the chain break is real (not a schema
> migration artifact) and that the affected user is a paying customer
> with EU data subjects in their workspace.

## Walk-through agenda

1. **Detection (T+0 → T+5 min)**
   - Where did the alert land? Who acknowledged it?
   - Did the audit pipeline correctly upgrade the incident severity to
     `critical` because of the chain break?
2. **Containment (T+5 → T+30 min)**
   - Revoke all sessions for the target user.
   - Revoke every API key created in the affected window.
   - Disable JIT API-key creation for that account pending review.
   - Snapshot the `security_audit_events` rows and the JSONL sink files
     for the affected window into the evidence locker.
3. **Investigation (T+30 min → T+4 h)**
   - Reproduce the chain break: which row's `event_hash` was wrong, and
     why?
   - Confirm whether the underlying breach involved EU personal data
     (yes per scenario) — start the **GDPR 72 h** timer.
   - Confirm whether US PHI was touched — if any HIPAA-covered data is
     in the workspace, start the **60 day** timer.
   - Walk through the customer's signed DPA to identify any
     contractual notification SLA tighter than the regulatory ones.
4. **Communication (T+4 h → T+24 h)**
   - Draft the customer notification. Validate it states: what happened,
     what data was affected, what we did, what they should do.
   - Draft the regulator notification. Confirm it can be sent before the
     72 h GDPR clock expires from the **confirmation** time, not just
     detection.
   - Decide whether public disclosure is warranted.
5. **Recovery & post-incident review (T+1 day → T+7 days)**
   - Verify all SLAs from the severity matrix were met.
   - Identify detection gaps (e.g. did `detection_impossible_travel`
     fire ahead of `detection_audit_chain_break`?).
   - File preventive actions with owners and due dates.

## Findings template

For each agenda item, capture:

- **What worked.** Specific people / systems / docs that helped.
- **What didn't.** Specific gaps observed during the drill.
- **Follow-up.** Owner, due date, and the SEC-### or task ID it links to.

## Post-drill artifacts to preserve

- The completed walk-through notes (this file, with findings filled in).
- A diff of any runbook updates the drill prompted.
- A list of newly opened follow-up tasks.
- Confirmation that the next quarterly drill is scheduled.
