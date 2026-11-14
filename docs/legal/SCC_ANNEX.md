# Standard Contractual Clauses — Annex (TEMPLATE)

> Annex to the Standard Contractual Clauses (Commission Implementing
> Decision (EU) 2021/914), incorporated by reference in the DPA at
> `docs/legal/DPA_TEMPLATE.md`. Customer-specific values are filled in on
> contract execution. Last revision: 2026-04-19.

## Module selection

- **Module 2** (controller-to-processor) — default.
- **Module 3** (processor-to-processor) — when Customer is itself a
  processor for its end customers.

## Annex I.A — List of parties

- Data exporter: Customer (Controller / Processor as relevant).
- Data importer: Manifest, Inc. (Processor).
  - Address: <to be filled>
  - Contact: dpo@manifest.example
  - Activities relevant to the data transferred: hosting, storage,
    transmission, AI-assisted processing, security monitoring.
  - Role: Processor (Module 2) or Sub-processor (Module 3).

## Annex I.B — Description of transfer

- Categories of data subjects: see DPA Annex I.
- Categories of personal data: see DPA Annex I.
- Sensitive data: only PHI under a separately executed BAA.
- Frequency: continuous.
- Nature of processing: hosting, storage, transmission, AI-assisted
  processing, security monitoring.
- Purpose: provision of the Manifest service.
- Retention: per `docs/security/DATA_RETENTION.md`.

## Annex I.C — Competent supervisory authority

For data exporters established in the EU, the competent supervisory
authority is the one identified per Clause 13. UK transfers: ICO.
Swiss transfers: FDPIC.

## Annex II — Technical and organisational measures

See DPA Annex II / `docs/security/TRUST_CENTER.md`.

## Annex III — Sub-processors

See `docs/privacy/SUB_PROCESSORS.md`. The customer authorisation under
DPA §6 constitutes the prior specific or general written authorisation
required by Clause 9(a).

## US Section 702 / Schrems II addendum

Manifest applies the following supplementary measures for transfers to
the United States in light of Schrems II:

- **Encryption at rest** with per-tenant DEKs; root keys managed by
  KMS; sub-processors do not have access to plaintext DEKs.
- **Encryption in transit** with TLS 1.2+, no plaintext fallback.
- **No bulk PHI transfers** outside an executed BAA.
- **Government-access transparency** — Manifest will challenge any
  request for personal data from public authorities that does not
  comply with EU law, will inform Customer to the extent legally
  permitted, and will publish an annual transparency report.
- **Audit log** of all access to Customer data.

## UK Addendum

The UK Addendum to the EU SCCs (issued by the ICO under s.119A DPA
2018) is incorporated by reference for transfers from the UK.

## Swiss amendments

For transfers from Switzerland, references to "Member State", "GDPR"
and the "Court of Justice of the European Union" are read to include
"Switzerland", "FADP" and the "Swiss Federal Supreme Court" as
applicable; the FDPIC is the competent supervisory authority.
