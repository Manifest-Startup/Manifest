# Record of Processing Activities (RoPA)

GDPR Art. 30 record. Reviewed quarterly. Last updated: 2026-04-19.

## 1. Controller / Processor

| Role | Entity | Contact |
|---|---|---|
| Controller (customer data shared by end users) | Manifest | privacy@manifest.example |
| Processor (data submitted by enterprise customers under DPA) | Manifest | dpo@manifest.example |
| Joint controller arrangements | None |  |

Data Protection Officer: dpo@manifest.example
EU representative (Art. 27): TBD on first EU enterprise contract.
UK representative: TBD on first UK enterprise contract.

## 2. Processing activities

| # | Purpose | Categories of data subjects | Categories of personal data | Lawful basis | Recipients | Retention | Cross-border transfer |
|---|---|---|---|---|---|---|---|
| P1 | Account creation & authentication | End users, admins | Email, hashed password, MFA secrets, session tokens, IP hash, UA | Contract (Art. 6(1)(b)) | Hosting (Replit), Postgres (Supabase) | Account lifetime + 30d after deletion request | EU↔US (SCCs) |
| P2 | Product usage (ideas, patents, voice agent transcripts) | End users | User-submitted content; field-level encrypted with per-tenant DEK | Contract | OpenAI (transient inference), Gemini (transient inference) | Until user deletes; crypto-shred on erasure | EU↔US (SCCs + Section 702 mitigations) |
| P3 | Security monitoring & audit | All identified subjects | Hash-chained audit log: actor, action, target, IP hash, UA | Legitimate interest (Art. 6(1)(f)) — fraud / abuse prevention | Internal SIEM | 1 year hot, 7 year cold archive | EU↔US (SCCs) |
| P4 | Service email (transactional) | Account holders | Email, name | Contract | SMTP provider | Until account deletion | EU↔US (SCCs) |
| P5 | Marketing email (opt-in only) | Subscribers | Email, name | Consent (Art. 6(1)(a)) | ESP | Until withdrawal of consent | EU↔US (SCCs) |
| P6 | Product analytics (opt-in / non-EEA opt-out) | Visitors, users | Pseudonymous visitor_id, page paths, IP hash | Consent (EEA) / Legitimate interest (other) | Internal warehouse | 13 months | EU↔US (SCCs) |
| P7 | Customer support | Account holders | Tickets, screenshots, attached PII | Contract | Internal support | 2 years from last interaction | EU↔US (SCCs) |
| P8 | Legal / compliance / DSAR fulfilment | All subjects | DSAR records, deletion certificates | Legal obligation (Art. 6(1)(c)) | DPO, regulator on request | 7 years | EU only |
| P9 | Billing & invoicing | Account holders | Name, billing address, last-4 of card (via Stripe) | Contract / Legal obligation | Stripe | 7 years (tax law) | EU↔US (SCCs) |

## 3. Special categories (Art. 9)

Manifest does not solicit or intentionally process special-category data.
Health-related data submitted by users under a signed BAA is treated as PHI
and falls under the HIPAA program — see `docs/security/HIPAA_PROGRAM.md`.

## 4. Children

Manifest is not directed at children under 16 (EEA) / 13 (US). The signup
flow includes an age gate — see `docs/privacy/PRIVACY_POLICY.md`.

## 5. Security measures (summary)

See `docs/security/TRUST_CENTER.md` for the full control inventory:
- TLS 1.2+ in transit, AES-256-GCM at rest with per-tenant DEKs.
- Crypto-shred-backed right-to-erasure (T3).
- Hash-chained, fail-closed audit logging (T14).
- TOTP + WebAuthn MFA; mandatory MFA for admin (T11).
- Per-route rate limiting and step-up re-auth on sensitive actions.

## 6. Review cadence

- Quarterly review by the DPO (calendar reminder owned by Compliance).
- On every new sub-processor, integration, or processing purpose.
- After every Sec/Privacy incident with personal-data impact.
