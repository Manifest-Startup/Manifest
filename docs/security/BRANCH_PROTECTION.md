# Branch Protection — Settings as Code

**Status:** v1.0
**Last updated:** 2026-04-19
**Owner:** Security Team
**Applies to:** `Manifest-Startup/Manifest` (this repository).

This document is the **authoritative description** of the branch-protection
ruleset for `main`. GitHub does not yet expose a fully declarative
`settings.yml` for everything we configure, so the canonical state lives here
and is verified quarterly during the access review (see `ACCESS_REVIEW.md`).

A drift between this document and the actual ruleset is a **finding** —
record under `SEC-058` and remediate before the next deploy.

---

## 1. Protected branch: `main`

### 1.1 Pull request requirements

| Setting                                                         | Value                                  |
| --------------------------------------------------------------- | -------------------------------------- |
| Require a pull request before merging                           | ✅                                     |
| Require approvals                                               | **2**                                  |
| Dismiss stale pull request approvals when new commits are pushed| ✅                                     |
| Require review from Code Owners                                 | ✅ (see `.github/CODEOWNERS`)          |
| Require approval of the most recent reviewable push             | ✅                                     |
| Require conversation resolution before merging                  | ✅                                     |
| Allowed merge methods                                           | **Squash + merge only** (linear history) |
| Automatically delete head branches                              | ✅                                     |

### 1.2 Status check requirements

All of the following must pass on the PR's head SHA before merge. Job names
mirror the `name:` field of the corresponding workflow job — keep this list
synchronized whenever a workflow `name:` changes (a one-character drift will
silently disable the required check).

> **2026-11-14:** the CI test and scanner gates (`main.yml`, PR/push triggers of `security.yml`) were removed in favour of local `python3 scripts/check.py`. `main` has no required status checks; `autopilot` requires none either. The lists below are historical.

From `.github/workflows/main.yml`:
- `🐍 Run Backend Tests (pytest)`
- `🧩 Run MCP Server Tests`
- `🛠️ Run Developer Tooling Tests`
- `🧰 Run Editor Extension Checks`
- `⚛️ Run Frontend Tests (Jest)`
- `📦 Bundle budget + Lighthouse CI`
- `🧪 Run E2E Tests (Cypress with Backend)`
- `Security dependency audits`

From `.github/workflows/security.yml`:
- `🔐 Secret scan (gitleaks)`
- `🐍 Python SAST (bandit + semgrep)`
- `⚛️  Frontend SAST (semgrep + eslint-security)`
- `🐍 Python SCA (pip-audit)`
- `⚛️  Frontend SCA (npm audit + osv-scanner)`
- `📜 License compliance (advisory)`
- `📦 SBOM (CycloneDX)`
- `🐳 Container scan (hadolint + trivy)`

> **Advisory-mode caveat:** while the security-workflow jobs use
> `continue-on-error: true`, they still **publish a check** that branch
> protection requires to **complete** (not necessarily pass). When a job is
> flipped to blocking, no branch-protection change is required — the existing
> required check now fails the PR.

| Setting                                                              | Value           |
| -------------------------------------------------------------------- | --------------- |
| Require status checks to pass before merging                         | ✅              |
| Require branches to be up to date before merging                     | ✅              |
| Allow merge with stale base if all required checks have run on the merge commit | ❌      |

### 1.3 Commit signing & history

| Setting                                              | Value                            |
| ---------------------------------------------------- | -------------------------------- |
| Require signed commits                               | ✅ (GPG, SSH, or Sigstore)       |
| Require linear history                               | ✅                               |
| Allow force pushes                                   | ❌                               |
| Allow deletions                                      | ❌                               |
| Restrict pushes that create matching branches        | ✅ (only repo admins)            |

### 1.4 Bypass

| Who                                       | Bypass allowed?                    |
| ----------------------------------------- | ---------------------------------- |
| Repository admins                         | ❌ (admins also bound by rules)    |
| `Manifest-Startup/security` team          | ❌                                 |
| Anyone else                               | ❌                                 |

The ruleset's `enforcement: active` flag is on for all team members,
**including admins**. Emergency bypass (e.g. live-site issue) requires:

1. A signed-off rationale in the IR channel.
2. A retroactive PR + post-incident review within 7 days.
3. Filing under `SEC-058` (drift) for audit trail.

---

## 2. Tag protection

Pattern `v[0-9]*` is protected:

- Only the GitHub Actions identity for the `release` workflow may create.
- Force-update is disabled.
- Deletion is disabled.

This guarantees that the tag a customer verifies via `cosign` is the same
tag CI signed.

---

## 3. Repository-level settings

| Setting                                       | Value                                         |
| --------------------------------------------- | --------------------------------------------- |
| Visibility                                    | Public                                        |
| Forking                                       | ✅ (for community contributions)              |
| Workflow permissions: default `GITHUB_TOKEN`  | **Read-only** (write granted per-job)         |
| Allow GitHub Actions to create / approve PRs  | ❌                                            |
| Workflow permissions: from forks              | **Require approval for first-time contributors** |
| Secret-scanning + push protection             | ✅ on for the org                             |
| Dependabot alerts + security updates          | ✅                                            |
| Private vulnerability reporting               | ✅ (see `SECURITY.md`)                        |
| GitHub Advanced Security                      | ✅ (CodeQL, secret scanning, push protection) |

---

## 4. Environments

### 4.1 `production`

- Required reviewers: 2 (one Platform + one Security or Eng-Lead).
- Wait timer: 0 (no artificial delay; canary controls real safety).
- Deployment branches: protected branch `main` and tags matching `v*`.
- Environment secrets: short-lived OIDC-federated cloud roles only — no
  long-lived secrets.
- Visibility: members of `Manifest-Startup/security` and
  `Manifest-Startup/platform`.

### 4.2 `beta`

- Required reviewers: 1.
- Deployment branches: `main` and `v*-beta.*` tags.
- Otherwise mirrors `production`.

### 4.3 `staging`

- Required reviewers: 0 (auto-deploy on every `main` push).
- Deployment branches: `main` only.

---

## 5. Verification

Quarterly, during the access review:

1. Export the live ruleset:
   `gh api -X GET repos/Manifest-Startup/Manifest/rulesets > rulesets.json`
2. Diff against the values above.
3. Any drift → file `SEC-058` finding, remediate, attach the post-mortem
   to the next access-review minutes.

A scripted verifier runs daily in `.github/workflows/governance-verify.yml`
(advisory until 2026-08-02, then blocking — see the gate-flip table in
`FINDINGS_BACKLOG.md`).

## 6. Applying / re-applying the ruleset

The canonical applier is `scripts/apply_branch_protection.py`. It parses the
required-check list out of §1.2 (using the same regex the verifier uses, so
applier and verifier can never disagree) and POSTs / PUTs the ruleset via
`gh api`. Run it as a repo admin:

```bash
# Inspect the payload first.
python3 scripts/apply_branch_protection.py --dry-run

# Apply against the live repo (idempotent — safe to re-run).
gh auth login          # admin scope on Manifest-Startup/Manifest
python3 scripts/apply_branch_protection.py
```

After applying, trigger `.github/workflows/governance-verify.yml` and
confirm `Live ruleset diff vs. BRANCH_PROTECTION.md` reports zero findings.
Capture that run URL in the next access-review minutes as the evidence
required by the §5 process and by the `governance-verify::live-ruleset-diff`
gate-flip row.
