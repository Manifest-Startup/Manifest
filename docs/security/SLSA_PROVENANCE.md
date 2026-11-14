# SLSA Provenance — Generation & Verification

**Status:** v1.0
**Last updated:** 2026-04-19
**Owner:** Platform + Security
**Target level:** [SLSA v1.0 Build L3](https://slsa.dev/spec/v1.0/levels)
**Cross-references:** [`RELEASE_PLAYBOOK.md`](./RELEASE_PLAYBOOK.md),
[`BRANCH_PROTECTION.md`](./BRANCH_PROTECTION.md).

This document explains **why** Manifest generates SLSA provenance for every
release artifact, **how** it is produced, and **how** consumers (including our
own deploy pipeline) verify it before running the artifact.

---

## 1. Why

A signed artifact alone proves *who built it*. SLSA provenance proves
*what was built, from which source, by which workflow, with which inputs* —
the four facts an auditor needs to answer "could this artifact have been
tampered with between commit and deploy?"

For Manifest this matters because:

- A compromised CI workflow could push a backdoored container even if the
  source repository is clean.
- An insider with write access to a single repo secret could produce a
  release that "looks signed" without going through review.
- Customers running the MCP server in their own environment need a way to
  confirm the binary they downloaded matches the source we publish.

SLSA L3 closes these gaps by:

1. Requiring the build to run on a **hardened, hosted builder** (GitHub
   Actions, with the `slsa-github-generator` reusable workflow).
2. Producing **non-falsifiable provenance** signed by the builder's OIDC
   identity (not by us).
3. **Isolating** the build from the publish step so a compromised publisher
   cannot rewrite history.

---

## 2. How (build side)

The release workflow (forthcoming, tracked in `SEC-057`) wires up the
following reusable workflows from the SLSA framework:

| Artifact type     | Reusable workflow                                                                  |
| ----------------- | ---------------------------------------------------------------------------------- |
| Generic file      | `slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml` |
| Container image   | `slsa-framework/slsa-github-generator/.github/workflows/generator_container_slsa3.yml` |
| Python package    | `slsa-framework/slsa-github-generator/.github/workflows/builder_python_slsa3.yml`  |
| npm package       | `slsa-framework/slsa-github-generator/.github/workflows/builder_nodejs_slsa3.yml`  |

Each call:

1. Re-checks out the tagged commit on a fresh runner.
2. Builds the artifact using the documented build command.
3. Generates a **DSSE-wrapped in-toto provenance statement** describing:
   - `subject` — the artifact's `sha256` digest and name.
   - `predicateType` — `https://slsa.dev/provenance/v1`.
   - `buildType` — the reusable workflow URI + version.
   - `invocation` — the GitHub Actions context (workflow ref, run id, event).
   - `materials` — the source repo + commit + ref.
   - `metadata.completeness` — `parameters: true, environment: true`.
4. Signs the statement via Sigstore **keyless** mode using the workflow's
   short-lived OIDC token (no long-lived signing keys to leak).
5. Uploads the provenance alongside the artifact to:
   - GitHub Release (`*.intoto.jsonl` next to the artifact).
   - The container registry as an OCI attestation
     (`type: application/vnd.in-toto+json`).

---

## 3. How (verify side)

Every consumer **must** verify provenance before use. Our own deploy pipeline
(`production` environment, see `BRANCH_PROTECTION.md` §4.1) blocks the deploy
if any of these checks fail:

```bash
# 1. SLSA provenance verification (containers).
slsa-verifier verify-image ghcr.io/manifest-startup/backend:vX.Y.Z \
  --source-uri github.com/Manifest-Startup/Manifest \
  --source-tag vX.Y.Z \
  --builder-id "https://github.com/slsa-framework/slsa-github-generator/.github/workflows/generator_container_slsa3.yml@refs/tags/v2.0.0"

# 2. SLSA provenance verification (generic file, e.g. mcp wheel).
slsa-verifier verify-artifact manifest-mcp-X.Y.Z.whl \
  --provenance-path manifest-mcp-X.Y.Z.intoto.jsonl \
  --source-uri github.com/Manifest-Startup/Manifest \
  --source-tag vX.Y.Z

# 3. Sigstore cosign signature (defence-in-depth — in case slsa-verifier is
#    bypassed by future tooling).
cosign verify ghcr.io/manifest-startup/backend:vX.Y.Z \
  --certificate-identity-regexp "^https://github.com/Manifest-Startup/Manifest/" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com

# 4. SBOM presence.
cosign download attestation ghcr.io/manifest-startup/backend:vX.Y.Z \
  --predicate-type https://cyclonedx.org/bom > /dev/null
```

Any failure aborts the deploy and pages the on-call. See
[`RELEASE_PLAYBOOK.md`](./RELEASE_PLAYBOOK.md) §6 for rollback.

---

## 4. Customer verification (MCP server, etc.)

Customers installing `manifest-mcp` from PyPI can verify provenance without
trusting Manifest's signing infrastructure (only the public Sigstore root):

```bash
pip download --no-deps manifest-mcp==X.Y.Z
slsa-verifier verify-artifact manifest_mcp-X.Y.Z-py3-none-any.whl \
  --provenance-path manifest_mcp-X.Y.Z.intoto.jsonl \
  --source-uri github.com/Manifest-Startup/Manifest \
  --source-tag vX.Y.Z
```

We commit to maintaining a **stable verification recipe** (the four lines
above) for at least 24 months after a release.

---

## 5. Threat model

| Threat                                      | Mitigation                                                              |
| ------------------------------------------- | ----------------------------------------------------------------------- |
| Tampered source after tagging               | Tag protection (`BRANCH_PROTECTION.md` §2) + verifier checks `source-tag`. |
| Malicious build inside our CI               | SLSA L3 isolates the builder; provenance pins the reusable workflow ref.|
| Stolen long-lived signing key               | None to steal — Sigstore keyless OIDC binds identity to workflow run.   |
| Replay of an old provenance for a new image | `subject.digest` is bound to the artifact's `sha256`.                   |
| Sigstore CT log compromise                  | We pin the public Fulcio + Rekor roots and re-verify offline weekly.    |
| Insider with prod-deploy access             | Two-approver rule on `production` environment + audit log of approvals. |

---

## 6. Roadmap

The 2026 roadmap items tracked in [`FINDINGS_BACKLOG.md`](./FINDINGS_BACKLOG.md):

- `SEC-057` — Wire up the `release.yml` workflow that calls the SLSA
  reusable workflows for backend, frontend, MCP, and dev CLI.
- `SEC-071` — Publish a quarterly transparency report listing every
  release artifact's digest + provenance link.
- `SEC-072` — Mirror provenance to a tamper-evident long-term store
  (e.g. Sigstore TrustRoot Mirror) for 7-year SOC 2 retention.
