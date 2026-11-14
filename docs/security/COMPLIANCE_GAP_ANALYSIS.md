# Manifest Compliance Gap Analysis

**Status:** Draft v1.1  
**Last updated:** 2026-04-19  
**Scope:** SOC 2 (Security TSC, with hooks for Confidentiality/Privacy/Availability), ISO/IEC 27001:2022 Annex A (all 93 controls enumerated), HIPAA Security Rule (45 CFR §164.308–.316), GDPR (all data-protection-relevant articles enumerated), CCPA/CPRA.  
**Companion docs:** `THREAT_MODEL.md`, `FINDINGS_BACKLOG.md`, `INCIDENT_RESPONSE_RUNBOOK.md`.

Status legend:
- ✅ **Met** — control implemented and evidenced.
- 🟡 **Partial** — partially implemented or implemented but missing evidence/policy/operationalization.
- ❌ **Gap** — not implemented.
- ➖ **N/A** — out of scope or not applicable to current product surface.

Every Partial/Gap row links to one or more `SEC-###` findings in `FINDINGS_BACKLOG.md` and to the remediation stream (T2–T7 = Tasks #11–#16). "—" in the Findings column means no specific code-level finding is required, only a policy or evidence artifact.

### Evidence-pointer convention

Each row points to evidence in one of three forms (so an auditor can pull the artifact without guessing):

1. **Code/config evidence** — implicit in the **Findings** column. The acceptance criteria inside the linked `SEC-###` entry in `FINDINGS_BACKLOG.md` enumerate the file paths, tests, dashboards, and screenshots that constitute evidence when the finding is closed. For ✅ rows, the file path is given inline.
2. **Threat-model evidence** — for any control whose evidence is "we modeled this and accepted/mitigated the risk", the pointer is the corresponding section of `THREAT_MODEL.md` (e.g. §4.2 for OAuth, §4.18 for outbound email).
3. **Policy / process evidence (forthcoming)** — for rows whose evidence is a policy, register, or operational artifact that does not yet exist, the pointer is the **Owner** stream — that stream's deliverables include the artifact (typed in `docs/security/<artifact>.md`, `docs/privacy/<artifact>.md`, vendor evidence folder, etc.).

Where a row needs a more specific pointer than the convention provides, an explicit `Evidence:` note appears in the row.

---

## 1. SOC 2 — Trust Services Criteria (Common Criteria, full enumeration)

### CC1 — Control Environment

| Control | Status | Evidence | Findings | Owner |
|---------|--------|----------|----------|-------|
| **CC1.1** Demonstrates commitment to integrity and ethical values | 🟡 | `SOC2_READINESS.md` lists owners and cadence | — | T6 |
| **CC1.2** Board demonstrates independence from management and exercises oversight | 🟡 | Owner roles enumerated; no formal board minutes archived | — | T6 |
| **CC1.3** Establishes structures, reporting lines, authorities and responsibilities | 🟡 | Owner table in `SOC2_READINESS.md` | — | T6 |
| **CC1.4** Demonstrates commitment to attract, develop and retain competent individuals | ❌ | No security-training log or hiring-criteria policy | — | T6 |
| **CC1.5** Holds individuals accountable for internal control responsibilities | 🟡 | Implicit via owner table | — | T6 |

### CC2 — Communication and Information

| Control | Status | Evidence | Findings | Owner |
|---------|--------|----------|----------|-------|
| **CC2.1** Obtains or generates relevant, quality information for internal control | ✅ | App + audit logs; `THREAT_MODEL.md` | — | — |
| **CC2.2** Internally communicates information including objectives and responsibilities | 🟡 | `SOC2_READINESS.md` cadence | — | T6 |
| **CC2.3** Communicates with external parties on matters affecting internal control | ❌ | No trust center, no `SECURITY.md`, no `/.well-known/security.txt` | SEC-064 | T7 (disclosure surface) + T6 (trust center) |

### CC3 — Risk Assessment

| Control | Status | Evidence | Findings | Owner |
|---------|--------|----------|----------|-------|
| **CC3.1** Specifies suitable objectives | 🟡 | Stream goals encoded in tasks #11–#16 | — | T1 (this task), annual cadence |
| **CC3.2** Identifies risks to objectives and analyzes them | ✅ | `THREAT_MODEL.md` (this revision) | — | T1, annual cadence |
| **CC3.3** Considers potential for fraud | 🟡 | Domain-spoof trigger event captured (THREAT_MODEL §1) | SEC-048, SEC-069 | T5, T4 |
| **CC3.4** Identifies and assesses changes that could significantly affect the system | 🟡 | No formal change-impact-on-controls review yet | — | T7 (CI gates) + T6 (governance) |

### CC4 — Monitoring Activities

| Control | Status | Evidence | Findings | Owner |
|---------|--------|----------|----------|-------|
| **CC4.1** Selects, develops and performs ongoing/separate evaluations | ❌ | No SIEM, no detections, no metrics dashboards | SEC-047, SEC-048 | T5 |
| **CC4.2** Communicates internal control deficiencies | ❌ | No formal escalation channel for control deficiencies | — | T5 + T6 |

### CC5 — Control Activities

| Control | Status | Evidence | Findings | Owner |
|---------|--------|----------|----------|-------|
| **CC5.1** Selects and develops control activities to mitigate risks | 🟡 | Code-level controls strong; policies thin | — | T6 |
| **CC5.2** Selects and develops general controls over technology | 🟡 | CI exists; SAST/SCA/SBOM gaps | SEC-057, SEC-059, SEC-061 | T7 |
| **CC5.3** Deploys control activities through policies and procedures | ❌ | Information Security, Access Control, Change Management, Vendor Management policies missing | — | T6 |

### CC6 — Logical and Physical Access Controls

| Control | Status | Evidence | Findings | Owner |
|---------|--------|----------|----------|-------|
| **CC6.1** Implements logical access security software, infrastructure, and architectures | 🟡 | OAuth + password + MFA + sessions + audit | SEC-001, SEC-003, SEC-011, SEC-013, SEC-017 | T2, T4 |
| **CC6.2** Registers and authorizes new internal and external users | 🟡 | OAuth/email signup; no SCIM, no formal joiner workflow | SEC-008 | T2, T6 |
| **CC6.3** Authorizes, modifies, and removes access based on roles, responsibilities | ❌ | No RBAC, no role-change session invalidation | SEC-016, SEC-028, SEC-030, SEC-065 | T2 |
| **CC6.4** Restricts physical access to facilities and protected information assets | ➖ | Provider-managed (Replit, Supabase) | — | T6 (collect provider attestations) |
| **CC6.5** Discontinues logical and physical protections over physical assets after disposal | 🟡 | Soft-delete + deletion-request flow; no crypto-shred | SEC-049, SEC-052 | T3, T6 |
| **CC6.6** Implements logical access security measures to protect against external threats | 🟡 | TLS at edge | SEC-002 (no HSTS/CSP/COOP), SEC-029 (GraphQL introspection) | T4 |
| **CC6.7** Restricts the transmission, movement, and removal of information | 🟡 | Cookies HttpOnly+Secure; no DLP | SEC-035, SEC-036 | T4 |
| **CC6.8** Implements controls to prevent or detect unauthorized or malicious software | 🟡 | Dependabot referenced; SAST/SCA not enforced | SEC-057, SEC-059, SEC-060, SEC-061, SEC-062 | T7 |

### CC7 — System Operations

| Control | Status | Evidence | Findings | Owner |
|---------|--------|----------|----------|-------|
| **CC7.1** Detects and monitors system components and the operation of those components for vulnerabilities | ❌ | No vulnerability monitoring beyond Dependabot mention | SEC-059 | T7, T5 |
| **CC7.2** Monitors system anomalies that are indicative of malicious acts | ❌ | No detections | SEC-048 | T5 |
| **CC7.3** Evaluates security events to determine whether they could result in a failure | 🟡 | `security_audit_events` exists; no triage workflow | SEC-045, SEC-067 | T5 |
| **CC7.4** Responds to identified security incidents by executing a response program | 🟡 | Runbook present; severity matrix and timers missing | SEC-067 | T5 |
| **CC7.5** Identifies, develops and implements activities to recover from incidents | 🟡 | Runbook recovery section; no restore drills evidenced | SEC-052, SEC-068 | T5, T3 |

### CC8 — Change Management

| Control | Status | Evidence | Findings | Owner |
|---------|--------|----------|----------|-------|
| **CC8.1** Authorizes, designs, develops, configures, documents, tests, approves and implements changes | 🟡 | Git + CI exists; no signed-commit / approval log | SEC-058 | T7 |

### CC9 — Risk Mitigation

| Control | Status | Evidence | Findings | Owner |
|---------|--------|----------|----------|-------|
| **CC9.1** Identifies, selects and develops risk-mitigation activities for risks arising from potential business disruptions | 🟡 | RTO/RPO not documented | SEC-052 | T3, T5 |
| **CC9.2** Assesses and manages risks associated with vendors and business partners | 🟡 | Vendor checklist in `SOC2_READINESS.md`; no completed register | SEC-043 | T6 |

### Optional TSC categories (turn on after CC stable)

- **Confidentiality** C1.1 (encryption + classification), C1.2 (disposal of confidential information). Status: 🟡 / 🟡 → T3.
- **Privacy** P1.1–P8.1 (notice, choice, collection, use/retention/disposal, access, disclosure, quality, monitoring/enforcement). Status: mostly 🟡, some ❌ → T6. (Detailed mapping happens inside the Privacy stream itself.)
- **Availability** A1.1 (capacity), A1.2 (recovery), A1.3 (recovery testing). Status: 🟡 / 🟡 / ❌ → T5, T3.

---

## 2. ISO/IEC 27001:2022 — Annex A (all 93 controls)

### A.5 Organizational controls (37)

| ID | Control | Status | Findings | Owner |
|----|---------|--------|----------|-------|
| A.5.1 | Policies for information security | ❌ | — | T6 |
| A.5.2 | Information security roles and responsibilities | 🟡 | — | T6 |
| A.5.3 | Segregation of duties | ❌ | SEC-065 | T2 |
| A.5.4 | Management responsibilities | 🟡 | — | T6 |
| A.5.5 | Contact with authorities | ❌ | — | T6 (regulator + law-enforcement contact list) |
| A.5.6 | Contact with special interest groups | ❌ | — | T6 |
| A.5.7 | Threat intelligence | ❌ | SEC-048 | T5 |
| A.5.8 | Information security in project management | 🟡 | — | T6 |
| A.5.9 | Inventory of information and other associated assets | 🟡 | — | T3 (`DATA_CLASSIFICATION.md`) — section 3 of THREAT_MODEL is the seed |
| A.5.10 | Acceptable use of information and other associated assets | ❌ | — | T6 |
| A.5.11 | Return of assets | ❌ | — | T6 (HR offboarding) |
| A.5.12 | Classification of information | 🟡 | — | T3 |
| A.5.13 | Labelling of information | ❌ | — | T3 |
| A.5.14 | Information transfer | 🟡 | SEC-035, SEC-036, SEC-069 | T4, T6 |
| A.5.15 | Access control | 🟡 | SEC-011, SEC-016, SEC-028, SEC-065 | T2 |
| A.5.16 | Identity management | 🟡 | SEC-008, SEC-018 | T2 |
| A.5.17 | Authentication information | 🟡 | SEC-003, SEC-007, SEC-008, SEC-009, SEC-017, SEC-019 | T2, T3 |
| A.5.18 | Access rights | ❌ | SEC-016, SEC-028, SEC-030, SEC-065 | T2 |
| A.5.19 | Information security in supplier relationships | ❌ | SEC-043 | T6 |
| A.5.20 | Addressing information security within supplier agreements | ❌ | SEC-043 | T6 (DPAs) |
| A.5.21 | Managing information security in the ICT supply chain | ❌ | SEC-057, SEC-059, SEC-062 | T7 |
| A.5.22 | Monitoring, review and change management of supplier services | ❌ | — | T6 |
| A.5.23 | Information security for use of cloud services | 🟡 | — | T6 (Replit + Supabase posture file) |
| A.5.24 | Information security incident management planning and preparation | 🟡 | SEC-067 | T5 |
| A.5.25 | Assessment and decision on information security events | 🟡 | SEC-045, SEC-048 | T5 |
| A.5.26 | Response to information security incidents | 🟡 | SEC-067 | T5 |
| A.5.27 | Learning from information security incidents | 🟡 | SEC-068 | T5 (postmortem template) |
| A.5.28 | Collection of evidence | 🟡 | SEC-044, SEC-047 | T5 |
| A.5.29 | Information security during disruption | ❌ | — | T5, T3 (BCDR) |
| A.5.30 | ICT readiness for business continuity | ❌ | SEC-052 | T3, T5 |
| A.5.31 | Legal, statutory, regulatory and contractual requirements | 🟡 | — | T6 |
| A.5.32 | Intellectual property rights | 🟡 | — | T6 (open-source license register) |
| A.5.33 | Protection of records | 🟡 | SEC-044, SEC-047 | T5 (audit-log retention) |
| A.5.34 | Privacy and protection of PII | 🟡 | SEC-035, SEC-041, SEC-042, SEC-043, SEC-050 | T6, T3 |
| A.5.35 | Independent review of information security | ❌ | — | T6 (annual cadence; this doc seeds it) |
| A.5.36 | Compliance with policies, rules and standards for information security | ❌ | SEC-061 | T7 (CI gates as compliance enforcement) |
| A.5.37 | Documented operating procedures | 🟡 | — | T6 |

### A.6 People controls (8)

| ID | Control | Status | Findings | Owner |
|----|---------|--------|----------|-------|
| A.6.1 | Screening | ❌ | — | T6 (background-check policy) |
| A.6.2 | Terms and conditions of employment | ❌ | — | T6 |
| A.6.3 | Information security awareness, education and training | ❌ | — | T6 |
| A.6.4 | Disciplinary process | ❌ | — | T6 |
| A.6.5 | Responsibilities after termination or change of employment | ❌ | — | T6 |
| A.6.6 | Confidentiality or non-disclosure agreements | 🟡 | — | T6 (NDA templates exist in `legal/`) |
| A.6.7 | Remote working | ❌ | — | T6 |
| A.6.8 | Information security event reporting | 🟡 | — | T5, T6 |

### A.7 Physical controls (14)

Almost entirely **➖ Provider-managed** by Replit and Supabase. The Manifest obligation is to **collect and retain** the providers' SOC 2 / ISO 27001 attestations and confirm scope coverage. Owner: T6.

| ID | Control | Status | Findings | Owner |
|----|---------|--------|----------|-------|
| A.7.1 | Physical security perimeters | ➖ | — | T6 (vendor evidence) |
| A.7.2 | Physical entry | ➖ | — | T6 |
| A.7.3 | Securing offices, rooms and facilities | ➖ | — | T6 |
| A.7.4 | Physical security monitoring | ➖ | — | T6 |
| A.7.5 | Protecting against physical and environmental threats | ➖ | — | T6 |
| A.7.6 | Working in secure areas | ➖ | — | T6 |
| A.7.7 | Clear desk and clear screen | ❌ | — | T6 (workforce policy — applies even to remote staff) |
| A.7.8 | Equipment siting and protection | ➖ | — | T6 |
| A.7.9 | Security of assets off-premises | ❌ | — | T6 (laptop policy / MDM) |
| A.7.10 | Storage media | ➖ | — | T6 |
| A.7.11 | Supporting utilities | ➖ | — | T6 |
| A.7.12 | Cabling security | ➖ | — | T6 |
| A.7.13 | Equipment maintenance | ➖ | — | T6 |
| A.7.14 | Secure disposal or re-use of equipment | 🟡 | — | T6 (laptop wipe procedure) |

### A.8 Technological controls (34)

| ID | Control | Status | Findings | Owner |
|----|---------|--------|----------|-------|
| A.8.1 | User endpoint devices | ❌ | — | T6 (MDM policy) |
| A.8.2 | Privileged access rights | ❌ | SEC-065, SEC-066 | T2 |
| A.8.3 | Information access restriction | 🟡 | SEC-030, SEC-038 | T2, T4 |
| A.8.4 | Access to source code | 🟡 | SEC-058 | T7 |
| A.8.5 | Secure authentication | 🟡 | SEC-003, SEC-007, SEC-008, SEC-009, SEC-017, SEC-018, SEC-019 | T2 |
| A.8.6 | Capacity management | 🟡 | — | T5 (SLOs) |
| A.8.7 | Protection against malware | 🟡 | SEC-039, SEC-062 | T4, T7 |
| A.8.8 | Management of technical vulnerabilities | 🟡 | SEC-053, SEC-059 | T7 |
| A.8.9 | Configuration management | 🟡 | SEC-006, SEC-056 | T3 |
| A.8.10 | Information deletion | 🟡 | SEC-049, SEC-052 | T3, T6 |
| A.8.11 | Data masking | ❌ | SEC-034, SEC-035, SEC-046 | T4, T5 |
| A.8.12 | Data leakage prevention | ❌ | SEC-035 | T4 |
| A.8.13 | Information backup | 🟡 | SEC-052 | T3 |
| A.8.14 | Redundancy of information processing facilities | 🟡 | — | T3, T5 |
| A.8.15 | Logging | 🟡 | SEC-022, SEC-045, SEC-046 | T5 |
| A.8.16 | Monitoring activities | ❌ | SEC-047, SEC-048 | T5 |
| A.8.17 | Clock synchronization | 🟡 | — | T5 |
| A.8.18 | Use of privileged utility programs | 🟡 | SEC-065 | T2 |
| A.8.19 | Installation of software on operational systems | 🟡 | SEC-058, SEC-062 | T7 |
| A.8.20 | Networks security | 🟡 | SEC-001, SEC-004, SEC-036 | T4 |
| A.8.21 | Security of network services | 🟡 | SEC-002, SEC-005 | T4 |
| A.8.22 | Segregation of networks | 🟡 | SEC-051 | T3 |
| A.8.23 | Web filtering | ➖ | — | Provider-managed |
| A.8.24 | Use of cryptography | 🟡 → ❌ | SEC-006, SEC-007, SEC-012, SEC-019, SEC-049, SEC-050 | T3 |
| A.8.25 | Secure development life cycle | 🟡 | — | T7 |
| A.8.26 | Application security requirements | 🟡 | (covered by all T4 findings) | T4 |
| A.8.27 | Secure system architecture and engineering principles | 🟡 | — | T4 |
| A.8.28 | Secure coding | 🟡 | SEC-061 | T7 |
| A.8.29 | Security testing in development and acceptance | 🟡 | SEC-061 | T7 |
| A.8.30 | Outsourced development | ➖ | — | None at this time |
| A.8.31 | Separation of development, test and production environments | 🟡 | SEC-055 | T3 |
| A.8.32 | Change management | 🟡 | SEC-058 | T7 |
| A.8.33 | Test information | 🟡 | — | T3 (no PII in test fixtures) |
| A.8.34 | Protection of information systems during audit testing | 🟡 | — | T6 (auditor-access process) |

---

## 3. HIPAA Security Rule (45 CFR §164.308–.316) — full enumeration

Manifest does not intentionally process PHI today, but the voice agent and document-generation flows can ingest health-related content. The objective is to be **HIPAA-eligible** so a BAA can be signed without architectural rework.

R = Required; A = Addressable.

### §164.308 Administrative safeguards

| § | Standard / specification | R/A | Status | Findings | Owner |
|---|--------------------------|-----|--------|----------|-------|
| 308(a)(1)(i) | Security management process | R | 🟡 | — | T1 (this program) |
| 308(a)(1)(ii)(A) | Risk analysis | R | ✅ | — | T1 (`THREAT_MODEL.md`) |
| 308(a)(1)(ii)(B) | Risk management | R | 🟡 | (all) | T1 (`FINDINGS_BACKLOG.md`) |
| 308(a)(1)(ii)(C) | Sanction policy | R | ❌ | — | T6 |
| 308(a)(1)(ii)(D) | Information system activity review | R | 🟡 | SEC-045, SEC-047 | T5 |
| 308(a)(2) | Assigned security responsibility (Security Officer) | R | ❌ | — | T6 |
| 308(a)(3)(i) | Workforce security | R | ❌ | — | T6 |
| 308(a)(3)(ii)(A) | Authorization and/or supervision | A | ❌ | SEC-065 | T2, T6 |
| 308(a)(3)(ii)(B) | Workforce clearance procedure | A | ❌ | — | T6 |
| 308(a)(3)(ii)(C) | Termination procedures | R | ❌ | — | T6 |
| 308(a)(4)(i) | Information access management | R | 🟡 | SEC-030, SEC-065 | T2 |
| 308(a)(4)(ii)(A) | Isolating health-care clearinghouse functions | R | ➖ | — | N/A — not a clearinghouse |
| 308(a)(4)(ii)(B) | Access authorization | A | 🟡 | SEC-016, SEC-028 | T2 |
| 308(a)(4)(ii)(C) | Access establishment and modification | A | 🟡 | SEC-016 | T2 |
| 308(a)(5)(i) | Security awareness and training | R | ❌ | — | T6 |
| 308(a)(5)(ii)(A) | Security reminders | A | ❌ | — | T6 |
| 308(a)(5)(ii)(B) | Protection from malicious software | A | 🟡 | SEC-039, SEC-062 | T4, T7 |
| 308(a)(5)(ii)(C) | Log-in monitoring | A | ❌ | SEC-009, SEC-048 | T2, T5 |
| 308(a)(5)(ii)(D) | Password management | A | 🟡 | SEC-008, SEC-053 | T2 |
| 308(a)(6)(i) | Security incident procedures | R | 🟡 | SEC-067 | T5 |
| 308(a)(6)(ii) | Response and reporting | R | 🟡 | SEC-067, SEC-069 | T5 |
| 308(a)(7)(i) | Contingency plan | R | ❌ | SEC-052 | T3, T5 |
| 308(a)(7)(ii)(A) | Data backup plan | R | 🟡 | SEC-052 | T3 |
| 308(a)(7)(ii)(B) | Disaster recovery plan | R | ❌ | — | T3, T5 |
| 308(a)(7)(ii)(C) | Emergency mode operation plan | R | ❌ | — | T5 |
| 308(a)(7)(ii)(D) | Testing and revision procedures | A | ❌ | SEC-068 | T5 |
| 308(a)(7)(ii)(E) | Applications and data criticality analysis | A | 🟡 | — | T3 |
| 308(a)(8) | Evaluation | R | 🟡 | — | T1 (annual cadence) |
| 308(b)(1) | Business associate contracts and other arrangements | R | ❌ | SEC-043 | T6 |
| 308(b)(3) | Written contract or other arrangement | R | ❌ | SEC-043 | T6 |

### §164.310 Physical safeguards

➖ Provider-managed across the board (Replit, Supabase). Manifest's obligation is to retain the providers' HIPAA posture statements / BAA-eligibility attestations. Owner: T6.

| § | Standard / specification | R/A | Status | Findings | Owner |
|---|--------------------------|-----|--------|----------|-------|
| 310(a)(1) | Facility access controls | R | ➖ | — | T6 (vendor evidence) |
| 310(a)(2)(i) | Contingency operations | A | ➖ | — | T6 |
| 310(a)(2)(ii) | Facility security plan | A | ➖ | — | T6 |
| 310(a)(2)(iii) | Access control and validation procedures | A | ➖ | — | T6 |
| 310(a)(2)(iv) | Maintenance records | A | ➖ | — | T6 |
| 310(b) | Workstation use | R | ❌ | — | T6 |
| 310(c) | Workstation security | R | ❌ | — | T6 (laptop policy / MDM) |
| 310(d)(1) | Device and media controls | R | 🟡 | — | T6 |
| 310(d)(2)(i) | Disposal | R | 🟡 | SEC-049 | T3, T6 |
| 310(d)(2)(ii) | Media re-use | R | 🟡 | — | T6 |
| 310(d)(2)(iii) | Accountability | A | 🟡 | — | T6 |
| 310(d)(2)(iv) | Data backup and storage | A | 🟡 | SEC-052 | T3 |

### §164.312 Technical safeguards

| § | Standard / specification | R/A | Status | Findings | Owner |
|---|--------------------------|-----|--------|----------|-------|
| 312(a)(1) | Access control | R | 🟡 | SEC-030, SEC-038, SEC-065 | T2, T4 |
| 312(a)(2)(i) | Unique user identification | R | ✅ | — | — |
| 312(a)(2)(ii) | Emergency access procedure | R | ❌ | SEC-066 | T2, T5 (break-glass) |
| 312(a)(2)(iii) | Automatic logoff | A | 🟡 | SEC-016 | T2 |
| 312(a)(2)(iv) | Encryption and decryption | A | 🟡 | SEC-049, SEC-050 | T3 |
| 312(b) | Audit controls | R | 🟡 | SEC-044, SEC-045, SEC-047 | T5 |
| 312(c)(1) | Integrity | R | 🟡 | SEC-044 | T5 |
| 312(c)(2) | Mechanism to authenticate ePHI | A | 🟡 | — | T3 (content hashing) |
| 312(d) | Person or entity authentication | R | 🟡 → ❌ | SEC-003, SEC-008, SEC-017, SEC-018 | T2 |
| 312(e)(1) | Transmission security | R | 🟡 | SEC-002 | T4 |
| 312(e)(2)(i) | Integrity controls (in transit) | A | 🟡 | — | T4 |
| 312(e)(2)(ii) | Encryption (in transit) | A | 🟡 | SEC-002 (HSTS) | T4 |

### §164.314 Organizational requirements

| § | Standard / specification | R/A | Status | Findings | Owner |
|---|--------------------------|-----|--------|----------|-------|
| 314(a)(1) | Business associate contracts or other arrangements | R | ❌ | SEC-043 | T6 |
| 314(a)(2)(i) | BAA: implementation specifications — contract | R | ❌ | SEC-043 | T6 |
| 314(a)(2)(ii) | BAA: other arrangements | R | ➖ | — | T6 |
| 314(a)(2)(iii) | Sub-contractor BAAs | R | ❌ | SEC-043 | T6 |
| 314(b)(1) | Requirements for group health plans | R | ➖ | — | N/A |
| 314(b)(2) | Implementation specifications | R | ➖ | — | N/A |

### §164.316 Policies and procedures and documentation requirements

| § | Standard / specification | R/A | Status | Findings | Owner |
|---|--------------------------|-----|--------|----------|-------|
| 316(a) | Reasonable and appropriate policies and procedures | R | ❌ | — | T6 |
| 316(b)(1) | Documentation | R | 🟡 | — | T6 |
| 316(b)(2)(i) | Time limit (retain 6 years) | R | ❌ | — | T6 |
| 316(b)(2)(ii) | Availability | R | ❌ | — | T6 |
| 316(b)(2)(iii) | Updates (review periodically) | R | ❌ | — | T6 (annual review) |

---

## 4. GDPR — full data-protection-relevant article enumeration

### Chapter II — Principles

| Art. | Topic | Status | Findings | Owner |
|------|-------|--------|----------|-------|
| 5(1)(a) | Lawfulness, fairness, transparency | 🟡 | — | T6 |
| 5(1)(b) | Purpose limitation | 🟡 | — | T6 |
| 5(1)(c) | Data minimisation | 🟡 | — | T6 |
| 5(1)(d) | Accuracy | 🟡 | — | T6 |
| 5(1)(e) | Storage limitation (retention) | 🟡 | SEC-049 | T3, T6 |
| 5(1)(f) | Integrity and confidentiality | 🟡 | (T2/T3/T4 surface) | T2, T3, T4 |
| 5(2) | Accountability | 🟡 | — | T6 (RoPA, evidence) |
| 6 | Lawful basis for processing | 🟡 | — | T6 |
| 7 | Conditions for consent | 🟡 | — | T6 |
| 8 | Child's consent for information society services | 🟡 | — | T6 (age-gate review) |
| 9 | Special categories of personal data | 🟡 | — | T6 (DPIA for voice/AI flows) |
| 10 | Criminal-conviction data | ➖ | — | Not processed |
| 11 | Processing not requiring identification | ➖ | — | N/A |

### Chapter III — Rights of the data subject

| Art. | Topic | Status | Findings | Owner |
|------|-------|--------|----------|-------|
| 12 | Transparent information / modalities for exercising rights | 🟡 | SEC-042 | T6 |
| 13 | Information to be provided where data is collected from the subject | 🟡 | — | T6 (privacy policy refresh) |
| 14 | Information to be provided where data is not obtained from the subject | 🟡 | — | T6 |
| 15 | Right of access | ❌ | SEC-042 | T6 |
| 16 | Right to rectification | 🟡 | — | T6 |
| 17 | Right to erasure ("right to be forgotten") | 🟡 | SEC-049 | T3, T6 |
| 18 | Right to restriction of processing | ❌ | — | T6 |
| 19 | Notification obligation regarding rectification, erasure, restriction | ❌ | — | T6 |
| 20 | Right to data portability | 🟡 | — | T6 (machine-readable export) |
| 21 | Right to object | ❌ | — | T6 |
| 22 | Automated individual decision-making, including profiling | 🟡 | — | T6 (AI disclosures + opt-out from training) |

### Chapter IV — Controller and processor

| Art. | Topic | Status | Findings | Owner |
|------|-------|--------|----------|-------|
| 24 | Responsibility of the controller | 🟡 | — | T6 |
| 25 | Data protection by design and by default | 🟡 | — | T1 cadence |
| 26 | Joint controllers | ➖ | — | None today |
| 27 | Representatives of controllers/processors not in the EU | ❌ | — | T6 (if EU users) |
| 28 | Processor (DPA with sub-processors) | ❌ | SEC-043 | T6 |
| 29 | Processing under the authority of the controller | 🟡 | — | T6 |
| 30 | Records of processing activities (RoPA) | ❌ | SEC-043 | T6 |
| 31 | Cooperation with the supervisory authority | ❌ | — | T6 |
| 32 | Security of processing | 🟡 | (all of T2/T3/T4/T5) | T2, T3, T4, T5 |
| 33 | Notification of a personal-data breach to the supervisory authority (72h) | 🟡 | SEC-067 | T5, T6 |
| 34 | Communication of a personal-data breach to the data subject | 🟡 | SEC-067 | T5, T6 |
| 35 | Data protection impact assessment (DPIA) | ❌ | — | T6 (DPIA for AI + voice agent) |
| 36 | Prior consultation with the supervisory authority | ❌ | — | T6 |
| 37 | Designation of the Data Protection Officer | 🟡 | — | T6 (assess Art. 37 thresholds) |
| 38 | Position of the DPO | 🟡 | — | T6 |
| 39 | Tasks of the DPO | 🟡 | — | T6 |

### Chapter V — Transfers

| Art. | Topic | Status | Findings | Owner |
|------|-------|--------|----------|-------|
| 44 | General principle for transfers | ❌ | SEC-051 | T3, T6 |
| 45 | Transfers on the basis of an adequacy decision | ❌ | — | T6 |
| 46 | Transfers subject to appropriate safeguards (SCCs, BCRs) | ❌ | — | T6 (SCCs with sub-processors) |
| 47 | Binding corporate rules | ➖ | — | N/A |
| 48 | Transfers or disclosures not authorised by Union law | 🟡 | — | T6 |
| 49 | Derogations for specific situations | 🟡 | — | T6 |

---

## 5. CCPA / CPRA — full consumer-rights enumeration

| Right / requirement | Cite | Status | Findings | Owner |
|---------------------|------|--------|----------|-------|
| Notice at collection | §1798.100(b) | 🟡 | — | T6 |
| Right to know — categories collected | §1798.110 | ❌ | SEC-042 | T6 |
| Right to know — specific pieces | §1798.110 | ❌ | SEC-042 | T6 |
| Right to delete | §1798.105 | 🟡 | SEC-049 | T3, T6 |
| Right to correct | §1798.106 | ❌ | — | T6 |
| Right to opt out of sale of personal information | §1798.120 | 🟡 | — | T6 (downstream enforcement on PostHog/ads) |
| Right to opt out of sharing for cross-context behavioral advertising | §1798.120(a) | 🟡 | — | T6 |
| Right to limit use of sensitive personal information | §1798.121 | ❌ | — | T6 |
| Right to non-discrimination for exercising rights | §1798.125 | 🟡 | — | T6 |
| Right to opt-in for minors (under 16; under 13) | §1798.120(c) | ❌ | — | T6 |
| Honoring Global Privacy Control (GPC) signal | §999.315(c) (CPRA regs) | ❌ | — | T6 |
| 45-day response timer (extendable +45) | §1798.130(a)(2) | ❌ | SEC-042 | T6 |
| Verifiable consumer request (VCR) workflow | §1798.130(a)(7) | ❌ | — | T6 |
| Two designated request methods (e.g. web form + email/phone) | §1798.130(a)(1) | ❌ | — | T6 |
| Privacy policy CCPA/CPRA addendum (12-month look-back) | §1798.130(a)(5) | ❌ | — | T6 |
| Service-provider / contractor / third-party contracts | §1798.140(j), (ag), (ai) | ❌ | SEC-043 | T6 |
| Risk assessments and cybersecurity audits (CPRA — once regs final) | §1798.185(a)(15) | ❌ | — | T6 (pending agency rules) |
| Annual privacy-rights metrics disclosure (>10M records threshold) | §999.317(g) | ➖ | — | Reassess yearly |
| Recordkeeping of consumer requests (24-month minimum) | §999.317(b) | ❌ | — | T6 |

---

## 6. Summary score

Counts use only in-scope rows (excluding ➖).

| Framework | ✅ | 🟡 | ❌ | ➖ | In-scope total | Coverage % (✅ + 🟡 of in-scope) |
|-----------|----|----|----|----|----------------|----------------------------------|
| SOC 2 Common Criteria | 1 | 14 | 7 | 1 | 22 | ~68% |
| ISO 27001 Annex A — A.5 | 0 | 17 | 20 | 0 | 37 | ~46% |
| ISO 27001 Annex A — A.6 | 0 | 2 | 6 | 0 | 8 | ~25% |
| ISO 27001 Annex A — A.7 | 0 | 1 | 2 | 11 | 3 | ~33% |
| ISO 27001 Annex A — A.8 | 0 | 28 | 5 | 1 | 33 | ~85% |
| HIPAA §164.308 | 1 | 11 | 17 | 1 | 29 | ~41% |
| HIPAA §164.310 | 0 | 5 | 2 | 5 | 7 | ~71% |
| HIPAA §164.312 | 1 | 10 | 1 | 0 | 12 | ~92% |
| HIPAA §164.314 | 0 | 0 | 3 | 3 | 3 | 0% |
| HIPAA §164.316 | 0 | 1 | 4 | 0 | 5 | ~20% |
| GDPR Ch. II–V | 1 | 19 | 13 | 4 | 33 | ~61% |
| CCPA/CPRA | 0 | 4 | 14 | 1 | 18 | ~22% |

**Read this as:** the **technical baseline** (HIPAA §164.312, ISO A.8) is decent because the codebase already implements the easy and medium-effort technical controls. The **operational / policy / evidence / rights-fulfillment** layers (CC1, A.5, A.6, HIPAA §164.308/.314/.316, CCPA/CPRA, GDPR rights articles) are the long tail. The remediation streams are sized accordingly: T2/T3/T4 close the technical gaps; T5/T6/T7 close the operational ones.

---

## 7. Audit-engagement readiness

Do not engage an external auditor (CPA / ISO certification body) until:

1. All **Critical** findings in `FINDINGS_BACKLOG.md` are closed (SEC-001 through SEC-006, SEC-069).
2. At least one full quarter of the `SOC2_READINESS.md` cadence has run end-to-end with evidence captured.
3. T5 is complete (audit-log streaming + IR runbook upgrade + one tabletop drill executed).
4. T6 is complete to the point of: published trust center, working DSAR endpoints, RoPA + sub-processor list + DPA template + SCCs, breach-notification workflow.

For HIPAA, additionally: Security & Privacy Officers designated, BAA template approved by counsel, training log started, contingency plan documented and tested.

For ISO 27001, additionally: ISMS scope statement, Statement of Applicability (SoA) with justification for any A-control deemed N/A, and one internal audit cycle completed.

For CCPA/CPRA, additionally: VCR workflow live, GPC honored end-to-end, two designated request methods, 12-month look-back in privacy policy, recordkeeping for 24 months.
