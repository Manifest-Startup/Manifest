# Manifest Security Policy

**Last updated:** 2026-04-19
**Maintained by:** Manifest Security Team — `security@manifeststartup.com`
**Public disclosure surface:** [`/.well-known/security.txt`](./.well-known/security.txt)

We take the security of Manifest, our customers, and the broader open-source ecosystem seriously. This document is the authoritative source for **how to report a vulnerability**, **what is in scope**, **our service-level commitments**, and the **safe-harbor** we extend to good-faith researchers.

---

## 1. Reporting a vulnerability

If you believe you have found a security vulnerability in any Manifest product, **please do not open a public GitHub issue**. Use one of the channels below. We will acknowledge receipt within one business day.

| Channel                  | Address / Link                                                | When to use                                          |
| ------------------------ | ------------------------------------------------------------- | ---------------------------------------------------- |
| Email (preferred)        | `security@manifeststartup.com`                                | All reports, including PII / customer-impact issues. |
| Encrypted email (PGP)    | `security@manifeststartup.com` — see [PGP key](#pgp-key)      | Reports containing exploit details, PoCs, or PII.    |
| GitHub private advisory  | <https://github.com/Manifest-Startup/Manifest/security/advisories/new> | Reports about this repository specifically.          |
| Postal mail (last resort)| Manifest Startup, Attn: Security, see contact form            | For physical evidence or notarized communications.   |

Please include, where possible:
- A clear description of the issue and its impact.
- Reproduction steps, proof-of-concept code, screenshots or video.
- The affected product (`manifeststartup.com`, `api.manifeststartup.com`, `manifest-mcp`, mobile app, etc.) and version / commit.
- Any indication of whether the issue is being actively exploited.
- How you would like to be credited (or whether you wish to remain anonymous).

We support **coordinated disclosure**: please give us a reasonable window (see [SLA](#3-service-level-commitments)) before publishing.

---

## 2. Scope

### 2.1 In scope

| Asset                                                      | Notes                                                              |
| ---------------------------------------------------------- | ------------------------------------------------------------------ |
| `manifeststartup.com` and all subdomains                   | Production web app, marketing site, docs, status page.             |
| `api.manifeststartup.com`                                  | REST + GraphQL + Socket.IO surface.                                |
| `manifest-mcp` Python package and the MCP server           | Including all MCP tools and command-line entry points.             |
| Manifest mobile clients (iOS, Android)                     | Latest store version only.                                         |
| Source code in this repository                             | `main` branch and any tagged release in the last 12 months.        |
| Container images published under `ghcr.io/manifest-startup/*` | Latest `:stable` and `:edge` tags.                              |
| Authentication, session, consent, and DSAR flows           | Account takeover, PII exposure, consent bypass — high priority.    |
| Build pipeline / CI workflows in `.github/workflows/`      | Issues that allow supply-chain compromise of releases.             |

### 2.2 Out of scope

The following are **explicitly out of scope** for our coordinated disclosure program. Reports about these will be acknowledged but are unlikely to qualify for credit.

- Findings on third-party services we use (Supabase, OpenAI, Stripe, Replit, GitHub, etc.) — please report directly to the vendor.
- Social engineering attacks against employees, contractors, customers, or vendors.
- Physical attacks against Manifest offices or staff.
- Denial-of-service via volumetric / brute-force traffic.
- Findings that require a compromised end-user device, browser extension, or rooted/jailbroken phone.
- Missing best-practice headers on non-authenticated marketing endpoints with no demonstrable impact.
- Outdated software versions without a working PoC against Manifest.
- Reports generated solely by automated scanners with no validation.
- Self-XSS, missing rate limits on idempotent reads, clickjacking on pages with no sensitive actions.
- Issues in `*.local`, `localhost`, ephemeral PR preview environments, or test fixtures.

### 2.3 Permitted research activities

Within scope, you may:
- Test against production using **your own** account(s).
- Create test accounts you control for the purpose of the research.
- Read your own data, including via APIs you have authenticated to.

You **must not**:
- Access, modify, or destroy data belonging to other users.
- Run intrusive scans (heavy fuzzers, brute-force, DoS) against production.
- Pivot beyond the proof-of-concept needed to demonstrate impact.
- Exfiltrate data beyond what is necessary to confirm a finding (e.g. one record is enough).
- Use the vulnerability to access more than is required for the report; cease activity once impact is established.
- Violate any applicable law, including the CFAA, GDPR, CCPA, HIPAA, or local equivalents.

---

## 3. Service-level commitments

| Stage                  | Target                                                      |
| ---------------------- | ----------------------------------------------------------- |
| Acknowledge receipt    | **1 business day**                                          |
| Initial triage + severity assignment | **3 business days**                           |
| Status updates         | At least every **7 calendar days** until resolved           |
| Critical fix deployed  | **7 calendar days** from confirmation                       |
| High fix deployed      | **30 calendar days**                                        |
| Medium fix deployed    | **90 calendar days**                                        |
| Low fix deployed       | Tracked in [`docs/security/FINDINGS_BACKLOG.md`](./docs/security/FINDINGS_BACKLOG.md) |
| Public disclosure window | **90 days** from initial report (extendable on request)   |

Severity is assessed using **CVSS 3.1** plus business-context modifiers (PII exposure, audit-control impact, regulatory blast radius). The mapping to our internal `SEC-###` finding stream is documented in [`docs/security/FINDINGS_BACKLOG.md`](./docs/security/FINDINGS_BACKLOG.md).

---

## 4. Safe harbor

Manifest will not initiate or support legal action against researchers who:

1. Make a **good-faith effort** to comply with this policy and the [permitted activities](#23-permitted-research-activities) above.
2. Avoid privacy violations, destruction of data, and degradation of user experience.
3. Use only the access necessary to confirm the vulnerability.
4. Give us a **reasonable time** to remediate before public disclosure (see [SLA](#3-service-level-commitments)).
5. Do not exploit the vulnerability beyond what is required for the report.

If your activity is consistent with this policy, we consider it **authorized** for the purposes of the U.S. Computer Fraud and Abuse Act (CFAA), the U.K. Computer Misuse Act, the EU NIS2 / GDPR Art. 32 lawful-research carve-outs, and similar statutes worldwide. We will affirmatively assert this authorization if a third party (including law enforcement) initiates action against you for activity conducted under this policy.

If at any point you are uncertain whether a particular activity is in scope, **stop and ask first** at `security@manifeststartup.com` — we would much rather field a question than receive an apology.

---

## 5. Recognition

We do not currently operate a paid bug bounty, but we do maintain a **public hall of fame** for valid reports. With your permission, we will:

- Credit you in `docs/security/HALL_OF_FAME.md` and the release notes for the fix.
- Provide a Manifest swag pack for High and Critical findings (postage permitting).
- Reference your report when publishing the corresponding CVE / GitHub Security Advisory.

A formal bug-bounty program with monetary rewards is on our roadmap — see [`docs/security/RELEASE_PLAYBOOK.md`](./docs/security/RELEASE_PLAYBOOK.md) for status.

---

## 6. Coordinated disclosure & CVE handling

For any confirmed vulnerability with security impact, we will:

1. Open a private GitHub Security Advisory on this repository.
2. Request a CVE through the GitHub CNA (or assign internally if more appropriate).
3. Develop and test a fix in the private advisory branch.
4. Publish the advisory, fix, and release notes simultaneously.
5. Notify affected customers via email and the in-product trust center if there is any chance of customer-data impact, in line with GDPR Art. 33/34, HIPAA Breach Notification Rule, and applicable U.S. state breach laws.

---

## 7. Supply chain & build integrity

Our build and release pipeline is part of our security surface. See:

- [`docs/security/RELEASE_PLAYBOOK.md`](./docs/security/RELEASE_PLAYBOOK.md) — tagging, signing, SBOM, rollback.
- [`docs/security/SLSA_PROVENANCE.md`](./docs/security/SLSA_PROVENANCE.md) — provenance generation and verification.
- [`docs/security/BRANCH_PROTECTION.md`](./docs/security/BRANCH_PROTECTION.md) — branch-protection settings as code.
- [`.github/workflows/security.yml`](./.github/workflows/security.yml) — SAST / SCA / SBOM / secret-scan gates.
- [`.github/dependabot.yml`](./.github/dependabot.yml) — automated dependency updates.
- [`docs/security/SECRET_ROTATION.md`](./docs/security/SECRET_ROTATION.md) — emergency rotation playbook.

If you have found an issue in any of the above, treat it as **High** by default — supply-chain compromise has higher blast radius than a single-tenant bug.

---

## <a name="pgp-key"></a>8. PGP key

Use the following key to encrypt sensitive reports. Verify the fingerprint out-of-band before sending PII / exploit details.

- **User ID:** `Manifest Security <security@manifeststartup.com>`
- **Fingerprint:** *not yet published — see operational note below*
- **Key file (planned):** `/.well-known/pgp-key.asc` (will be committed once the ceremony is complete)
- **Key servers (planned):** keys.openpgp.org, keys.gnupg.net

> **Operational note (2026-04-19):** the production PGP key is generated in a hardware-backed signing ceremony (see [`SECRET_ROTATION.md`](./docs/security/SECRET_ROTATION.md) §6). Until that ceremony is complete the project does **not** publish a PGP key — please use the GitHub private advisory channel for any report containing exploit details. We deliberately omit `/.well-known/pgp-key.asc` and the matching `Encryption:` line in `security.txt` rather than advertising an endpoint that does not yet exist. The fingerprint and ASCII-armored public key will be committed to this repository and announced on the trust center. **Do not trust any PGP key not committed to this repository.**

---

## 9. Contact summary

| Need                          | Where to go                                              |
| ----------------------------- | -------------------------------------------------------- |
| Report a vulnerability        | `security@manifeststartup.com` or GitHub private advisory |
| Subscribe to security updates | <https://manifeststartup.com/trust>                      |
| Sub-processor list / DPA      | <https://manifeststartup.com/legal>                      |
| Press / coordinated disclosure| `press@manifeststartup.com` (cc `security@…`)            |

Thank you for helping keep Manifest and our customers safe.
