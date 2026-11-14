# Personal-data Breach Notification Procedure

Owner: DPO + Security on-call. Last updated: 2026-04-19.

## 1. Definitions

A *personal-data breach* is "a breach of security leading to the
accidental or unlawful destruction, loss, alteration, unauthorised
disclosure of, or access to, personal data" (GDPR Art. 4(12)). For
HIPAA, a *breach* is an impermissible use or disclosure of PHI that
compromises the security or privacy of the PHI (45 CFR §164.402).

## 2. Statutory clocks

| Regime | Notify regulator within | Notify data subjects within | Internal trigger |
|---|---|---|---|
| GDPR Art. 33/34 | 72 hours of awareness | Without undue delay if high risk | T+0 hours |
| UK GDPR | 72 hours | Without undue delay if high risk | T+0 hours |
| HIPAA Breach Notification Rule | 60 days (large) / annual (small) | 60 days (individuals) | T+0 hours |
| CCPA / CPRA | "in the most expedient time" | Without unreasonable delay | T+0 hours |
| US state laws (incl. NY SHIELD, MA 93H) | Varies — track separately | Varies | T+0 hours |

T+0 = the moment a confirmed incident is escalated to Sev1 in the
incident-response runbook (`docs/security/INCIDENT_RESPONSE_RUNBOOK.md`,
T14) and tabletop exercises (`docs/security/INCIDENT_TABLETOP_2026Q2.md`).

## 3. Workflow

1. **Detect** — security audit chain alerts, SIEM alerts, customer
   reports, sub-processor notifications.
2. **Triage (within 1h)** — on-call confirms scope, declares Sev,
   opens war room, assigns Incident Commander.
3. **Contain (within 4h)** — revoke credentials, rotate secrets,
   crypto-shred compromised DEKs if necessary, isolate affected hosts.
4. **Assess (within 24h)** — DPO classifies as personal-data breach
   yes/no and risk-tier (low / medium / high) using the decision tree
   in §4.
5. **Notify regulator (within 72h GDPR / per matrix)** — DPO files via
   the lead supervisory authority's portal; HHS via the OCR portal.
   Use the template in §5.
6. **Notify data subjects (per matrix)** — if high risk to rights and
   freedoms, contact each affected user. Use the template in §6.
7. **Remediate** — patch root cause, run a tabletop on the incident
   class, update the threat model.
8. **Post-mortem (within 14 days)** — blameless write-up published to
   the incident archive; lessons fed into the DPIA review.

## 4. Risk-tier decision tree

- *High risk* if: special-category data, financial data, credentials,
  >100 EU residents, or unencrypted plaintext leak.
- *Medium* if: pseudonymous identifiers + behavioural data leak.
- *Low* if: data was encrypted at rest with KMS-backed keys not
  exposed in the breach (rebuttable safe-harbour).

## 5. Regulator notification template (GDPR Art. 33)

```
Subject: Personal data breach notification — Manifest

1. Nature of the breach
   - Date/time of awareness:
   - Date/time of incident (if known):
   - Categories of personal data affected:
   - Approximate number of data subjects:
   - Approximate number of records:

2. Likely consequences for the data subjects

3. Measures taken or proposed to address the breach and mitigate
   adverse effects

4. Contact point
   - DPO: dpo@manifest.example
   - Security: security@manifest.example
```

## 6. Data-subject notification template

```
Subject: Important security notice from Manifest

We are writing to let you know about a security incident that may have
affected your Manifest account.

What happened: <plain-language summary>
When we discovered it: <date>
What information was involved: <categories>
What we are doing: <containment + remediation>
What you can do: <password reset, MFA, monitor accounts>
Contact: privacy@manifest.example
```

## 7. Sub-processor breach handling

Sub-processor contracts require notification within 24h of awareness.
On receipt, the DSP triggers the workflow above with the sub-processor
incident treated as the source.

## 8. Records

Every breach (whether notifiable or not) is recorded in the breach
register held by the DPO. The register is reviewed at the quarterly
privacy review and made available to auditors.
