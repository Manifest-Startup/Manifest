# Data Processing Addendum (TEMPLATE)

> Template — incorporated by reference into the Master Subscription
> Agreement when the customer is a controller of personal data subject
> to GDPR, UK GDPR, Swiss FADP or comparable law. Last revision:
> 2026-04-19.

## 1. Roles

Customer is the **Controller** and Manifest is the **Processor** for
all personal data processed under the MSA, except where Manifest acts
as a Controller for its own legitimate business purposes (e.g.
billing, security monitoring), as set out in the Privacy Policy.

## 2. Subject matter, duration, nature and purpose

Subject matter and duration: the term of the MSA.
Nature and purpose: the provision of the Manifest service as described
in the MSA, including hosting, storage, transmission, AI-assisted
processing, and security monitoring.
Categories of data subjects and personal data: Annex I.
Special categories: only where Customer enables PHI processing under
the BAA.

## 3. Processor obligations

Manifest shall:
- Process personal data only on documented instructions from Customer.
- Ensure persons authorised to process the data are bound by
  confidentiality.
- Implement the technical and organisational measures in Annex II
  (TOMs).
- Engage sub-processors only with the authorisations set out in §6.
- Assist Customer in fulfilling DSARs (see `/api/dsar` endpoints).
- Assist Customer with security, breach notification, DPIA and prior
  consultation obligations.
- At Customer's choice, return or delete personal data upon end of the
  MSA.
- Make available all information necessary to demonstrate compliance
  with this DPA, including audit reports.

## 4. International transfers

Where personal data is transferred from the EEA, UK or Switzerland to
a third country without an adequacy decision, the Standard Contractual
Clauses (SCCs) — Module 2 (controller-to-processor) or Module 3
(processor-to-processor) — apply, with the parameters in Annex III
(`docs/legal/SCC_ANNEX.md`). The UK Addendum and Swiss amendments apply as
relevant.

## 5. Data-subject requests

Manifest shall, taking into account the nature of the processing,
assist Customer by appropriate technical and organisational measures
to fulfil DSARs. The /api/dsar endpoints enable Customer to fulfil
access, portability, rectification, objection and erasure requests
directly.

## 6. Sub-processors

Customer authorises Manifest to engage the sub-processors listed at
`docs/privacy/SUB_PROCESSORS.md`. Manifest will give at least 30 days'
prior notice of any addition. Customer may object on reasonable
data-protection grounds; if the parties cannot resolve the objection,
Customer may terminate the affected services.

## 7. Audit rights

Customer may, on 30 days' notice and no more than once per year (more
often where mandated by a regulator), audit Manifest's compliance
with this DPA. Manifest may satisfy such audits by providing a SOC 2
Type II report.

## 8. Breach notification

Manifest shall notify Customer without undue delay, and in any event
within 24 hours of confirmation, of any personal-data breach affecting
Customer's data, with the information required for Customer to comply
with its own GDPR Art. 33/34 obligations.

## 9. Liability

Liability under this DPA is governed by the limitations in the MSA.

## 10. Order of precedence

In the event of conflict: SCCs > this DPA > MSA.

---

### Annex I — Categories of data subjects and personal data

- Data subjects: Customer's end users, employees, contractors.
- Personal data: account identifiers, content uploaded to the service,
  usage telemetry, support correspondence.
- Special categories: only PHI under a separately executed BAA.

### Annex II — Technical and organisational measures (TOMs)

See `docs/security/TRUST_CENTER.md`. Highlights: TLS 1.2+, AES-256-GCM
at rest with per-tenant DEKs, crypto-shred on erasure, hash-chained
audit log, MFA, least-privilege RBAC, dependency + SAST + secret
scanning in CI, 24/7 incident response.

### Annex III — SCC parameters

See `docs/legal/SCC_ANNEX.md`.
