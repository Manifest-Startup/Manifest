# Data Protection Impact Assessment (DPIA)

Required by GDPR Art. 35. Conducted for processing activities that
present a high risk to data subjects: P2 (LLM-assisted product features)
and P3 (security monitoring).

Owner: DPO. Last reviewed: 2026-04-19. Next review: 2026-10.

## 1. Description of the processing

- **Activity P2 — LLM-assisted product features.** User content
  (ideas, drafts, patent text, voice transcripts) is sent transiently
  to OpenAI / Gemini under contracts that disable training and enforce
  zero data retention. Content is encrypted at rest under a per-tenant
  DEK; the DEK is crypto-shredded on right-to-erasure.
- **Activity P3 — Security monitoring & audit.** Every authentication,
  privilege change and data-access event is recorded in a hash-chained,
  append-only log. PII is redacted at the writer boundary (emails are
  recorded as `email:<sha256-prefix>` only).

## 2. Necessity & proportionality

- The LLM processing is the core service — users explicitly invoke it.
- The audit log is the minimum required for SOC 2 CC7.2, ISO 27001
  A.8.15 and HIPAA §164.312(b). Severity is calibrated so non-security
  events are not collected.

## 3. Risks identified

| # | Risk | Likelihood | Impact | Residual after mitigation |
|---|---|---|---|---|
| R1 | Provider re-uses prompt content for training | Low | High | Low — contract + zero-retention API tier |
| R2 | Audit log leaks PII | Low | High | Very low — PII redaction at writer + offline encryption |
| R3 | Crypto-shred fails to render data unrecoverable | Very low | High | Very low — DEK deletion happens in same transaction as plaintext scrub; audit row mandatory |
| R4 | DSAR endpoint abused for account takeover | Medium | High | Low — authenticated session + email-confirmation + step-up where applicable |
| R5 | Sub-processor breach | Low | High | Low — vendor due diligence, DPA, SCCs, breach-notification SLA in contract |

## 4. Mitigations in place

- Per-tenant data encryption keys; per-row encryption for high-sensitivity columns.
- Crypto-shred + hard-delete on erasure (T3 + DSAR /erase route).
- Hash-chained audit log with offline verifier and SIEM mirroring (T14).
- Vendor risk: contractual zero-retention; quarterly sub-processor review.
- DSAR rate-limiting and email re-confirmation on destructive endpoints.

## 5. Consultation

The DPIA is shared with security@, engineering, and legal counsel.
Where residual risk remains medium or higher, the DPO consults the lead
supervisory authority before launch (Art. 36).

## 6. Review triggers

- Adding any new LLM provider.
- Changing the lawful basis for any activity.
- Material schema or workflow change affecting categories of data.
- After any reportable incident.
