# Manifest Secret Rotation Playbook

**Status:** v1.0
**Last updated:** 2026-04-19
**Owner:** Security Team (`security@manifeststartup.com`)
**Cross-references:**
- [`ENCRYPTION_AND_KEY_MANAGEMENT.md`](./ENCRYPTION_AND_KEY_MANAGEMENT.md)
- [`INCIDENT_RESPONSE_RUNBOOK.md`](./INCIDENT_RESPONSE_RUNBOOK.md)
- [`AUDIT_LOGGING.md`](./AUDIT_LOGGING.md)
- [`FINDINGS_BACKLOG.md`](./FINDINGS_BACKLOG.md) — SEC-056 tracks gaps.

This playbook is the **single source of truth** for rotating any credential,
key, or token used by Manifest. It is invoked:

1. On a fixed **scheduled cadence** (§2 table below).
2. When a **secret-scanner alert** or external researcher reports a leak (§4).
3. As part of the **incident-response** flow when compromise is suspected (§5).
4. When **personnel change** (offboarding, role change). See `ACCESS_REVIEW.md`.

> **Golden rule:** the value of a rotation is in the *attestation* and the
> *blast-radius reduction* — not in the rotation itself. Always log who rotated
> what, when, and how the old credential was invalidated.

---

## 1. Inventory of secrets

The authoritative inventory lives in our secrets manager. The categories below
match the structure of `.github/workflows/security.yml` and the production
config in `backend/app/config/settings.py`.

| # | Secret                                | Where it lives                                  | Used by                                  | Rotation cadence | Owner             |
| - | ------------------------------------- | ----------------------------------------------- | ---------------------------------------- | ---------------- | ----------------- |
| 1 | `SUPABASE_SERVICE_ROLE_KEY`           | GH `secrets`, prod env, dev `.env`              | Backend admin DB access, migrations      | **90 days**      | Platform          |
| 2 | `SUPABASE_JWT_SECRET`                 | GH `secrets`, prod env                          | Backend session verification             | **90 days**      | Platform          |
| 3 | `OPENAI_API_KEY`                      | Replit Integration → prod env                   | AI features                              | **180 days**     | AI                |
| 4 | `GOOGLE_API_KEY` (Gemini)             | GH `secrets`, prod env                          | Pitch reels, video                        | **180 days**     | AI                |
| 5 | `SESSION_SECRET`                      | Prod env, dev `.env`                            | Session signing                          | **180 days**     | Security          |
| 6 | `MANIFEST_AGENT_LOOP_SECRET`          | Internal env only                               | Agent-loop internal routes                | **90 days**      | Platform          |
| 7 | `MANIFEST_GITHUB_TOKEN`               | GH `secrets`                                    | Internal feedback / website-audit loops  | **180 days**     | Platform          |
| 8 | `POSTHOG_API_KEY`                     | Prod env                                        | Analytics                                | **365 days**     | Growth            |
| 9 | API-Key records (`api_keys` table)    | Postgres (hashed at rest)                       | Customer-facing API auth                 | **365 days max** | Customer          |
|10 | OIDC client secrets (Replit, SSO)     | Prod env                                        | Replit OIDC / customer SSO                | **180 days**     | Security          |
|11 | TLS certificates                      | CDN / load-balancer                             | HTTPS                                    | Auto (Let's Encrypt 60d) | Platform |
|12 | DKIM private keys                     | Email provider (Postmark / SendGrid)            | Outbound email signing                   | **365 days**     | Platform          |
|13 | PGP private key (`security@`)         | YubiKey + offline backup                        | Vulnerability-report decryption          | **730 days**     | Security          |
|14 | Database backup encryption keys       | Cloud KMS                                       | Restore-from-backup                      | **365 days**     | Platform          |
|15 | Repository-signing GPG / Sigstore key | Sigstore (keyless OIDC)                         | Release artifact signing                 | Per-build (ephemeral) | Security    |
|16 | Webhook signing secrets (Stripe etc.) | Prod env                                        | Inbound webhook verification             | **180 days**     | Platform          |
|17 | Per-user MFA recovery codes           | Customer-controlled                             | Account recovery                          | On use           | Customer          |

If a credential exists in production but is not in the table above, file
`SEC-056` against this document — the inventory is intended to be exhaustive.

---

## 2. Scheduled rotations

The schedule is enforced by a recurring calendar invite ("Manifest Secret
Rotation Window") on the 1st business day of every month. Each window:

1. Pulls the inventory table above into a checklist.
2. Filters to credentials whose `last_rotated_at + cadence ≤ today + 14d`.
3. Executes the rotation procedure (§3) for each.
4. Files the attestation (§7) and closes the calendar item.

A rotation that misses its window by **>30 days** is automatically escalated to
the on-call Security responder and tracked in `FINDINGS_BACKLOG.md`.

---

## 3. Generic rotation procedure

For each secret in scope:

1. **Pre-flight**
   - Confirm a current backup of the secret store.
   - Confirm the on-call channel is staffed.
   - Identify all consumers (search code + infrastructure for the variable name).

2. **Generate the new value**
   - Use the provider's "rotate" action where available (Supabase, OpenAI,
     Stripe, GitHub Tokens API, GitHub Actions OIDC).
   - For self-managed values (`SESSION_SECRET`, `MANIFEST_AGENT_LOOP_SECRET`,
     webhook signing) use `python -c "import secrets; print(secrets.token_urlsafe(64))"`
     on a hardened workstation.
   - Never paste the value into chat, tickets, or email.

3. **Stage**
   - Add the new value to **production secrets** under a temporary alias
     (`<NAME>_NEXT`) or via dual-secret support if the consumer supports it.
   - Deploy a build that accepts **both** the old and new values during the
     transition window.

4. **Cut over**
   - Update the canonical environment variable to the new value.
   - Restart all dependent workflows / services.
   - Run the **smoke test** for that secret (e.g. issue a token, sign a webhook,
     query the DB) to confirm acceptance.

5. **Invalidate the old value**
   - Use the provider's "revoke" or "delete" action.
   - For `SESSION_SECRET`, **forcibly invalidate all active sessions** (see
     `INCIDENT_RESPONSE_RUNBOOK.md` §3.4) — this is a user-visible action and
     must be communicated on the status page.
   - Confirm by replaying a request with the old value and observing failure.

6. **Audit**
   - Confirm the rotation event landed in the central audit log.
   - File the attestation (§7).

7. **Cleanup**
   - Remove temporary aliases.
   - Update `last_rotated_at` in the secrets-manager metadata.

---

## 4. Emergency rotation (leak detected)

A "leak" is any of:

- A pre-commit / CI gitleaks finding on a value that matches a real secret.
- A push that briefly contained a secret, even if reverted.
- An external researcher report.
- A finding by HoundDog, GitHub Push Protection, GitGuardian, or similar.
- A laptop loss / suspected device compromise belonging to anyone with prod
  access.

**Procedure (T = time of detection):**

| T+    | Action                                                                                                                                  | Owner            |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| 0m    | Open `INCIDENT-<date>-<short>` in the IR channel; declare severity.                                                                    | First responder  |
| 5m    | Revoke the leaked secret at the provider. Confirm the new value rejects the old token.                                                  | Security on-call |
| 15m   | Generate replacement, deploy following §3 steps 2–5.                                                                                    | Platform on-call |
| 30m   | Force-rotate any secret that **shares** infrastructure with the leaked one (defence-in-depth — assume lateral compromise until proven). | Security on-call |
| 1h    | Run audit-log review for the affected secret's window of validity. Look for unusual access patterns.                                    | Security         |
| 4h    | Customer-impact assessment; trigger breach notification flow (`INCIDENT_RESPONSE_RUNBOOK.md`) if PII could have been accessed.          | Legal + Security |
| 24h   | Post-mortem draft. Add SEC-### finding for the *root cause*, not just the leak.                                                        | Security         |
| 7d    | Post-mortem published in `docs/security/`; backlog entry closed; attestation filed (§7).                                                | Security         |

For secrets that are part of the **build pipeline** (`GITHUB_TOKEN`,
deployment OIDC role, package-publishing tokens) treat all unsigned releases
made during the validity window as untrusted; verify SLSA provenance on each
deployed artifact and re-build / re-deploy from a known-good commit if the
provenance is in doubt. See `RELEASE_PLAYBOOK.md` §6.

---

## 5. Personnel-change rotation

When anyone with production access leaves the team, changes role, or has their
device replaced:

1. Disable their SSO + GitHub access (handled by `ACCESS_REVIEW.md`).
2. Within **24 hours**, rotate every shared secret they could have read while
   employed:
   - Production env vars (Supabase, OpenAI, Stripe, etc.).
   - GitHub Actions repo secrets.
   - Any credentials in `1Password` / shared vaults they had access to.
3. Issue new MFA enrollment for any service the departing user shared an
   account on.
4. File the attestation (§7) and link it to the offboarding ticket.

---

## 6. PGP signing-key ceremony

The `security@manifeststartup.com` PGP key handles inbound vulnerability
reports. It is generated once and rotated every **24 months**, or immediately
on suspicion of compromise.

**Ceremony summary** (full transcript stored in the security drive):

1. Two Security team members present, third witnesses on a recorded video call.
2. Generate Ed25519 / RSA-4096 sub-keys on a YubiKey 5 series in an offline
   environment (live-USB Linux, network disabled).
3. Master key escrowed to two geographically separated, tamper-evident
   envelopes with split passphrase (Shamir 2-of-3).
4. Public key published to:
   - `/.well-known/pgp-key.asc`
   - `keys.openpgp.org`
   - `keys.gnupg.net`
   - `SECURITY.md` PGP section (fingerprint).
5. Old key is **revoked** with a published revocation certificate; supersession
   notice posted on the trust center.
6. `last_rotated_at` updated in inventory (§1, row 13).

Until the first ceremony is complete, vulnerability reports containing exploit
details should use the GitHub private-advisory channel — see `SECURITY.md` §8.

### 6.1 Release-signing pubkeys (`RELEASE_SIGNERS_PUBKEYS`)

The `release.yml` workflow refuses to build/sign/publish unless the tag
that triggered it carries a valid PGP signature from an authorised
release signer. The list of authorised signers is materialised as the
GitHub Actions secret `RELEASE_SIGNERS_PUBKEYS` (organisation-scoped,
visible to the `Manifest` repo only).

- **Format:** ASCII-armored PGP public keys for every authorised
  release signer, concatenated with a single newline between each
  `-----END PGP PUBLIC KEY BLOCK-----` and the next
  `-----BEGIN PGP PUBLIC KEY BLOCK-----`. Order does not matter.
- **Provisioning:** copy each signer's exported public key
  (`gpg --armor --export <fpr>`) into the secret in the GitHub UI.
- **Rotation cadence:** on every personnel change (§5) and every 24
  months in lockstep with the `security@` PGP key.
- **Verification:** the workflow imports the secret into a fresh
  keyring on the runner, prints all imported fingerprints to the
  audit log, then runs `git verify-tag <tag>`. Unsigned tags, tags
  signed by a non-listed key, or a missing/empty secret all fail
  closed.

---

## 7. Attestation template

Every rotation (scheduled or emergency) MUST be recorded as an attestation in
the security audit log. Template (markdown front-matter compatible):

```yaml
secret_id: SUPABASE_SERVICE_ROLE_KEY
rotation_id: 2026-04-19T00:00:00Z-supabase-svc
trigger: scheduled        # scheduled | leak | personnel | incident-response
operator: alice@manifeststartup.com
witness:  bob@manifeststartup.com
old_value_invalidated_at: 2026-04-19T00:14:33Z
new_value_active_at:      2026-04-19T00:11:02Z
verification:
  - smoke_test_passed: true
  - old_value_rejects: true
  - audit_log_event_id: aud_evt_01HXYZ...
notes: |
  Routine 90-day rotation. No customer impact. Dual-secret window 3 minutes.
```

The attestation is committed to the security drive (not the public repo) and
the `audit_log_event_id` is linked back to it for post-hoc verification.

---

## 8. Backout

If a rotation causes a production outage:

1. Revert the consumer to accept the old value (dual-secret window).
2. Page the on-call for the affected service.
3. Treat as a Sev-2 incident; restore service before continuing the rotation.
4. Schedule a **make-up rotation** within 7 days; do not skip it.

A failed rotation is a finding (`SEC-###` against this playbook), not a
free pass — secrets that miss their cadence stay in `FINDINGS_BACKLOG.md`
until rotated.
