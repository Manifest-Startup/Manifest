# Manifest Trust Center

A single entry point for prospective customers, auditors, and security
researchers. The machine-readable mirror is exposed at
`GET /api/trust-center`.

Last updated: 2026-04-19.

## Frameworks

- **SOC 2 Type II** — controls in scope: Security, Confidentiality,
  Availability. Audit window opens once observation period closes.
- **ISO/IEC 27001:2022** — ISMS designed; certification engagement
  scoped.
- **GDPR** — implementation complete. RoPA, DPIA, breach procedure and
  DSAR endpoints in place.
- **CCPA / CPRA** — opt-out / DNS supported; GPC honoured.
- **HIPAA** — Business-Associate ready under signed BAA.

## Data subject rights (DSAR)

| Right | Endpoint |
|---|---|
| Access | `GET /api/dsar/access` |
| Portability | `GET /api/dsar/portability` |
| Rectification | `POST /api/dsar/rectify` |
| Object / opt-out | `POST /api/dsar/object` |
| Erasure | `POST /api/dsar/erase` |
| Consent | `GET|POST /api/privacy/consent` |

SLA: **30 calendar days** from authenticated request. Identity
verification is by authenticated session + email re-confirmation on
destructive actions.

## Security controls (summary)

- TLS 1.2+ everywhere; HSTS preload eligible.
- AES-256-GCM at rest, per-tenant DEKs wrapped by KMS root key.
- Crypto-shred on right-to-erasure: deleting the wrapped DEK renders
  every ciphertext unrecoverable. (T3 + T15.)
- Hash-chained, append-only audit log; offline verifier with chain-break
  detection mirrored to SIEM. (T14.)
- TOTP + WebAuthn MFA; admin requires MFA + step-up re-auth.
- Per-route rate limiting and global SSRF / response-splitting guards.
- Continuous dependency, SAST, and secret scanning in CI.

## Sub-processors

See `docs/privacy/SUB_PROCESSORS.md`. Customers are notified at least
30 days before any change.

## Contact

| Topic | Address |
|---|---|
| Privacy / DSAR | privacy@manifest.example |
| Security incidents | security@manifest.example |
| Responsible disclosure | security@manifest.example (PGP on request) |
| DPO | dpo@manifest.example |

## Document index

- `docs/privacy/PRIVACY_POLICY.md`
- `docs/privacy/TRACKING_AND_CONSENT.md`
- `docs/privacy/ROPA.md`
- `docs/privacy/SUB_PROCESSORS.md`
- `docs/privacy/DPIA.md`
- `docs/privacy/BREACH_NOTIFICATION.md`
- `docs/security/HIPAA_PROGRAM.md`
- `docs/security/DATA_RETENTION.md`
- `legal/BAA_TEMPLATE.md`
- `legal/DPA_TEMPLATE.md`
- `legal/SCC_ANNEX.md`
