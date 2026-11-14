#!/usr/bin/env python3
"""Apply the documented branch-protection ruleset to the live GitHub repo.

Source of truth: ``docs/security/BRANCH_PROTECTION.md``. This script builds a
GitHub Rulesets API payload that mirrors every machine-checkable field the
``governance-verify::live-ruleset-diff`` step asserts on, then POSTs (create)
or PUTs (update) it via the ``gh`` CLI.

Usage::

    # Dry-run: print the JSON payload without touching GitHub.
    python3 scripts/apply_branch_protection.py --dry-run

    # Apply against the default repo (Manifest-Startup/Manifest).
    GH_TOKEN=ghp_xxx python3 scripts/apply_branch_protection.py

    # Apply against a fork / staging org.
    python3 scripts/apply_branch_protection.py --repo my-org/Manifest

The caller must be authenticated as a repo admin (``gh auth status`` should
report admin scope), since branch rulesets require admin-level permissions.

The script is idempotent: if a ruleset named ``main-branch-protection``
already exists on the repo it is updated in place; otherwise a fresh one is
created. Re-running on a no-op produces no diff.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "security" / "BRANCH_PROTECTION.md"
RULESET_NAME = "main-branch-protection"
DEFAULT_REPO = "Manifest-Startup/Manifest"


def parse_required_checks(doc: str) -> list[str]:
    """Extract the §1.2 required-check job names from BRANCH_PROTECTION.md.

    The verifier in ``governance-verify.yml`` uses the exact same regex
    (``^- \\`([^`]+)\\``) — keep the two in sync so the applier and verifier
    can never disagree about which checks belong on the live ruleset.
    """
    return re.findall(r"^- `([^`]+)`", doc, re.M)


def build_ruleset_payload(required_checks: list[str]) -> dict[str, Any]:
    """Return the full Rulesets API body for the documented `main` ruleset."""
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",  # §1.4 — admins also bound
        "bypass_actors": [],  # §1.4 — no bypass for anyone
        "conditions": {
            "ref_name": {
                "include": ["refs/heads/main"],
                "exclude": [],
            }
        },
        "rules": [
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 2,  # §1.1
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": True,
                    "require_last_push_approval": True,
                    "required_review_thread_resolution": True,
                    # Squash-only is enforced repo-wide (allowed-merge-types)
                    # rather than per-rule; the verifier doesn't assert it
                    # here, see §1.1 footnote.
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,  # §1.2 up-to-date
                    "required_status_checks": [
                        {"context": c} for c in required_checks
                    ],
                },
            },
            {"type": "non_fast_forward"},          # §1.3 no force-push
            {"type": "deletion"},                  # §1.3 no deletion
            {"type": "required_linear_history"},   # §1.3 linear history
            {"type": "required_signatures"},       # §1.3 signed commits
        ],
    }


def gh(*args: str, input_data: str | None = None) -> subprocess.CompletedProcess:
    if shutil.which("gh") is None:
        sys.exit("error: `gh` CLI not found on PATH. Install from https://cli.github.com/")
    return subprocess.run(
        ["gh", *args],
        input=input_data,
        capture_output=True,
        text=True,
        check=False,
    )


def find_existing_ruleset_id(repo: str) -> int | None:
    res = gh("api", f"repos/{repo}/rulesets")
    if res.returncode != 0:
        sys.exit(f"error: failed to list rulesets on {repo}:\n{res.stderr}")
    for rs in json.loads(res.stdout or "[]"):
        if rs.get("name") == RULESET_NAME and rs.get("target") == "branch":
            return rs["id"]
    return None


def apply_ruleset(repo: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload)
    existing = find_existing_ruleset_id(repo)
    if existing is None:
        print(f"Creating ruleset {RULESET_NAME!r} on {repo}…")
        res = gh(
            "api", "-X", "POST",
            f"repos/{repo}/rulesets",
            "-H", "Accept: application/vnd.github+json",
            "--input", "-",
            input_data=body,
        )
    else:
        print(f"Updating existing ruleset id={existing} on {repo}…")
        res = gh(
            "api", "-X", "PUT",
            f"repos/{repo}/rulesets/{existing}",
            "-H", "Accept: application/vnd.github+json",
            "--input", "-",
            input_data=body,
        )
    if res.returncode != 0:
        sys.exit(f"error: GitHub API call failed:\n{res.stderr}")
    print("OK. Run `.github/workflows/governance-verify.yml` to confirm a clean diff.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", default=DEFAULT_REPO, help=f"owner/name (default: {DEFAULT_REPO})")
    p.add_argument("--dry-run", action="store_true", help="print payload, do not call GitHub")
    args = p.parse_args()

    if not DOC_PATH.exists():
        sys.exit(f"error: {DOC_PATH} not found — run from the repo root.")
    required_checks = parse_required_checks(DOC_PATH.read_text())
    if not required_checks:
        sys.exit("error: parsed zero required checks from BRANCH_PROTECTION.md")

    payload = build_ruleset_payload(required_checks)

    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0

    apply_ruleset(args.repo, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
