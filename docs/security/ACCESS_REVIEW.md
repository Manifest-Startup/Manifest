# Access Review Procedure

Owner: Security + Engineering managers. Cadence: quarterly.

## Scope

All accounts with access to:
- Production application (admin role).
- Production database (Supabase project owners / read-only viewers).
- Cloud provider consoles (Replit org owners, AWS, GCP).
- Source code repositories (GitHub org).
- Sub-processor admin consoles (Stripe, OpenAI, Gemini, SMTP).
- Secret stores (Replit secrets, KMS).

## Procedure

1. **Inventory.** Pull the current member/role list from each system
   into `docs/security/ACCESS_INVENTORY_<YYYY-Qn>.csv`.
2. **Reconcile.** For each row: confirm the person is still employed,
   still in a role that requires the access, and that any elevated
   privilege (admin / owner) is justified. Apply least-privilege.
3. **Remediate.** File a change ticket for any account that should be
   removed, demoted, or have MFA enforced. Target turnaround: 5 business
   days.
4. **Sign-off.** The Security Officer and the responsible Engineering
   manager sign the inventory. Store the signed PDF alongside the CSV.

## Off-boarding

Within **24 hours** of an employee leaving, all production access is
revoked, sessions invalidated, and personal API keys rotated. The
off-boarding checklist lives in the People Ops runbook.

## Onboarding gate

See `docs/security/TRAINING_LOG.md` — Security Awareness 101 + Privacy
Basics must be complete before any production access is granted.

## Evidence

The signed inventories are the SOC 2 CC6.2 / ISO 27001 A.5.18 evidence
artefacts. They are also reviewed by HIPAA-program scope every quarter.
