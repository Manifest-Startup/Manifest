# Manifest Release Playbook

**Status:** v1.0
**Last updated:** 2026-04-19
**Owner:** Platform Team (`platform@manifeststartup.com`) + Security Team
**Cross-references:**
- [`SLSA_PROVENANCE.md`](./SLSA_PROVENANCE.md)
- [`SECRET_ROTATION.md`](./SECRET_ROTATION.md)
- [`BRANCH_PROTECTION.md`](./BRANCH_PROTECTION.md)
- [`INCIDENT_RESPONSE_RUNBOOK.md`](./INCIDENT_RESPONSE_RUNBOOK.md)
- [`.github/workflows/security.yml`](../../.github/workflows/security.yml)

This playbook governs every Manifest release. Its goals are:

1. **Reproducibility** — any release tag can be rebuilt bit-for-bit.
2. **Provenance** — every artifact is signed and traceable to a specific
   commit, builder identity, and CI workflow run.
3. **Observability** — every change is described in the changelog and linked
   to the security findings it addresses.
4. **Recoverability** — every release has a documented rollback path and a
   pre-validated previous-known-good (PKG) version.

---

## 1. Release cadence

| Channel  | Cadence       | Tag pattern         | Audience                           |
| -------- | ------------- | ------------------- | ---------------------------------- |
| `edge`   | Every commit on `main` | `edge-<sha>` | Internal staging                   |
| `beta`   | Weekly (Tue)  | `vX.Y.Z-beta.N`     | Opt-in customers + design partners |
| `stable` | Bi-weekly     | `vX.Y.Z`            | All production customers           |
| `hotfix` | On-demand     | `vX.Y.(Z+1)`        | Targeted security/critical fixes   |

`vX.Y.Z` follows **semver**:
- **MAJOR** — breaking API change (also requires deprecation notice ≥ 90 days).
- **MINOR** — backwards-compatible feature.
- **PATCH** — bugfix or security fix only.

---

## 2. Pre-release checklist

The release manager (RM) must complete this checklist before tagging. The CI
workflow [`release.yml`](../../.github/workflows/release.yml) (tag-triggered
on `v*.*.*` and `v*.*.*-beta.*`, see SEC-057 closure) enforces the
machine-checkable items below — re-running the security baseline against
the tag SHA, verifying the tag's PGP signature against
`RELEASE_SIGNERS_PUBKEYS`, signing both the backend container and the
frontend tarball with Sigstore Cosign keyless, attaching SLSA v1.0
provenance, attaching CycloneDX SBOMs, and gating production deploy on the
two-approver `production` GitHub Environment. The human checklist items
below remain RM-owned.

- [ ] All `main` checks green: `CI – Manifest Full Stack` + `Security` workflows.
- [ ] No open `Critical` finding in [`FINDINGS_BACKLOG.md`](./FINDINGS_BACKLOG.md)
      that targets the release scope.
- [ ] `CHANGELOG.md` updated with sections: **Added / Changed / Fixed / Security
      / Deprecated / Removed**, each entry linked to a PR + issue.
- [ ] Database migrations reviewed; rollback plan documented in the changelog.
- [ ] Privacy / DSAR surface unchanged, OR DPIA addendum noted (Task #15).
- [ ] Sub-processor list unchanged, OR notification scheduled (`legal/`).
- [ ] Lockfiles up-to-date and clean (`uv.lock`, `package-lock.json`).
- [ ] SBOM diff reviewed against previous release (new transitive deps flagged).
- [ ] All secrets used by the release are within their rotation window
      ([`SECRET_ROTATION.md`](./SECRET_ROTATION.md) §1).

---

## 3. Tagging & signing

Tags are **annotated** and **GPG-signed** by the release manager:

```bash
git tag -s vX.Y.Z -m "Manifest vX.Y.Z

Highlights:
- ...

Security fixes: SEC-### (severity), SEC-### (severity)
Provenance:    https://github.com/Manifest-Startup/Manifest/actions/runs/<run>
SBOM:          attached to the GitHub Release
"
git push origin vX.Y.Z
```

Branch protection (see [`BRANCH_PROTECTION.md`](./BRANCH_PROTECTION.md))
requires signed commits on `main`, and the tag-pushing workflow refuses to
build unsigned tags.

The release workflow then:

1. Checks out the tag.
2. Re-runs the full security workflow (`security.yml`) against the tag SHA.
3. Builds the backend container, frontend assets, and any first-party
   packages (MCP server, dev CLI).
4. Generates the **CycloneDX SBOM** for each artifact.
5. Generates **SLSA v1.0 provenance** for each artifact via the
   `slsa-framework/slsa-github-generator` reusable workflow (see
   [`SLSA_PROVENANCE.md`](./SLSA_PROVENANCE.md)).
6. Signs each artifact with **Sigstore Cosign** in keyless mode (OIDC binding
   to the GitHub Actions identity for the release workflow).
7. Publishes the signed artifacts + provenance + SBOM to:
   - GitHub Release (primary).
   - `ghcr.io/manifest-startup/*` (container).
   - PyPI / npm (where applicable, with `--require-hashes`).

---

## 4. Verification (downstream)

Any consumer — including our own deployment pipeline — must verify before use:

```bash
# Verify Sigstore signature for the container.
cosign verify ghcr.io/manifest-startup/backend:vX.Y.Z \
  --certificate-identity-regexp "^https://github.com/Manifest-Startup/Manifest/.github/workflows/release.yml@" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"

# Verify SLSA provenance.
slsa-verifier verify-image ghcr.io/manifest-startup/backend:vX.Y.Z \
  --source-uri github.com/Manifest-Startup/Manifest \
  --source-tag vX.Y.Z

# Verify SBOM is attached.
cosign download attestation ghcr.io/manifest-startup/backend:vX.Y.Z \
  --predicate-type https://cyclonedx.org/bom \
  | jq .
```

Deployments that fail any of the three verifications **must not** roll out;
the release is treated as compromised until investigated.

---

## 5. Deploy

Production deploy is controlled by the `production` GitHub Environment, which:

- Requires **two human approvers** (one Platform + one Security or Eng-Lead).
- Restricts deploy to tags matching `v[0-9]+\.[0-9]+\.[0-9]+`.
- Issues short-lived OIDC-federated cloud credentials (no long-lived secrets).
- Blocks deploys from forks or from outside the protected branch ruleset.

Promotion order: `edge` → `beta` (24h soak) → `stable` (canary 5% → 25% → 100%
with 30-minute SLO observation between steps).

The production deploy step records a **deploy attestation** (release tag,
commit SHA, builder identity, deployer identity, timestamp) into the central
audit log. This satisfies the Task #14 "build provenance auditable in
production" criterion.

---

## 6. Rollback

A rollback is **fast** (≤ 10 minutes from decision to production-served PKG)
and **boring** (no manual changes — just re-deploy a previous tag):

1. Identify the **previous-known-good** tag (the most recent `stable` tag
   before the current one). The release workflow stores this in the GitHub
   Release notes for every release.
2. Trigger the `deploy` workflow with the PKG tag as input.
3. The workflow re-uses the **already-signed, already-verified** artifact —
   no rebuild — and runs the same SLSA + cosign checks as a fresh deploy.
4. Post-rollback:
   - File `INCIDENT-<date>-<short>` and follow `INCIDENT_RESPONSE_RUNBOOK.md`.
   - Add a `SEC-###` finding with the root cause; do not re-promote until
     the finding is closed.
   - Customer notification on `https://manifeststartup.com/trust` if the
     rollback was visible to users.

**Database rollbacks** are handled separately; migrations must be
backwards-compatible with at least the previous stable release. If a migration
is destructive, the changelog must call this out explicitly and the deploy
must be staged across two releases (forward + cleanup).

---

## 7. License & dependency policy

Allowed licenses (the CI license-scan job enforces this):

- **Allowed:** MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, Python-2.0,
  PostgreSQL, Unlicense, CC0-1.0, MPL-2.0 (with isolation review).
- **Disallowed:** GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0, AGPL-3.0, SSPL,
  Commons-Clause, BUSL-1.1, anything "non-commercial" only.
- **Review required:** any license not on the allowed or disallowed lists —
  Security + Legal sign off before merge.

A new transitive dependency that introduces a disallowed license **fails the
release** (currently advisory; flips to blocking per `FINDINGS_BACKLOG.md`).

---

## 8. Change-log conventions

`CHANGELOG.md` is the public record of changes; it follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/). Each release
has six sections (omit empty ones):

```
## [vX.Y.Z] — 2026-04-19
### Added
- ...
### Changed
- ...
### Fixed
- ...
### Security
- SEC-### (Severity): summary, reporter credit (with permission), CVE if any.
### Deprecated
- ...
### Removed
- ...
```

A **security entry without a reporter credit** must explain why (internal
finding, automated scanner) so external readers can trust the disclosure.

---

## 9. Bug-bounty roadmap

The current program is **vulnerability disclosure only** (see `SECURITY.md`).
A formal monetary bug-bounty program is gated on:

- [ ] CI security gates flipped to blocking (tracked in `FINDINGS_BACKLOG.md`).
- [ ] PGP key ceremony complete and key published.
- [ ] Triage SLA hit consistently for ≥ 1 quarter.
- [ ] Legal review of safe-harbor language for non-US jurisdictions.
- [ ] Funding approved for at least 12 months of payouts.

When all of the above are green, the program will be hosted on either GitHub
Security Advisories or a dedicated platform (HackerOne / Bugcrowd /
Intigriti). The selection decision lives in the Security drive.
