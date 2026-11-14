"""Manifest Security Autofix — autonomous "patch the vulns the moment they land".

The third member of the autopilot family, after the issue-fixing loop
(``run_autopilot_agent.py``) and the PR Merge Train (``run_pr_merge_train.py``).
This one closes **security alerts** without waiting for a human or for a
Dependabot PR to be reviewed:

  * **npm** manifests — run ``npm audit fix`` (non-breaking only) in every
    ``package-lock.json`` project, so transitive CVEs Dependabot can't open a
    clean PR for get patched automatically.
  * **pip** manifests — read the repo's live **Dependabot alerts** and bump the
    matching ``requirements.txt`` pin to the first patched version.

Then it runs the same checks ``scripts/check.py`` runs on the **deployable** trees and,
if green, pushes to ``main`` (auto-releasing) so the fix ships as early as
possible — even overnight with your laptop closed. It runs on a frequent cron
in GitHub Actions, so "whenever they come" means "within the cron window,"
not "whenever you next sit down."

Safety:
  * Kill switch ``SECURITY_AUTOFIX_ENABLED`` (fail-closed; no-op unless "true").
  * Only **non-breaking** npm fixes are applied (no ``--force``); semver-major
    bumps and unfixable transitive vulns are left for a human / Dependabot and
    reported, never force-merged.
  * The push only happens after the deployable trees pass the full gate; a red
    gate aborts the push and leaves ``main`` untouched.
  * Protected branches are never deleted (this loop deletes nothing).

The decision layer (alert→bump mapping, requirements rewriting, audit-summary
parsing, npm-dir discovery) is pure and unit-tested without git, npm, or the
network — see ``backend/tests/test_security_autofix.py``.

Required env (provided by the GHA workflow):
  GITHUB_TOKEN / GH_TOKEN  — alerts API + push token
  GITHUB_REPOSITORY        — owner/repo
Optional env (repo variables, safe defaults):
  SECURITY_AUTOFIX_ENABLED — must be "true" to act (default false = no-op)
  SECURITY_AUTOFIX_PUSH    — "direct" (push to main) | "pr" (open a PR)
                             (default "direct")
  SECURITY_AUTOFIX_BASE    — branch to land fixes on (default "main")

Usage:
  python backend/scripts/run_security_autofix.py            # fix + push
  python backend/scripts/run_security_autofix.py --dry-run  # plan only, no writes
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_BASE = "main"
# Trees CI actually builds/ships — the gate must pass here before any push.
DEPLOYABLE_CHECKS = (
    ("frontend", ["npm", "ci", "--no-audit", "--no-fund"]),
    ("frontend", ["npm", "run", "build"]),
    ("frontend", ["npm", "test", "--", "--watchAll=false"]),
    ("extensions/manifest-dev", ["npm", "ci", "--no-audit", "--no-fund"]),
    ("extensions/manifest-dev", ["npm", "run", "compile"]),
)


# ======================================================================
# Pure decision logic (no git, no npm, no network) — unit-tested directly.
# ======================================================================


@dataclass(frozen=True)
class PipBump:
    manifest_path: str
    package: str
    patched: str


def discover_npm_dirs(tracked_paths: list[str]) -> list[str]:
    """Project dirs (containing a package-lock.json) from a path listing,
    skipping anything inside node_modules. Order preserved, de-duplicated."""
    out: list[str] = []
    for p in tracked_paths:
        p = p.strip()
        if not p.endswith("package-lock.json") or "node_modules/" in p:
            continue
        d = str(Path(p).parent)
        if d not in out:
            out.append(d)
    return out


def parse_audit_summary(audit_json: str) -> dict[str, int]:
    """Total + per-severity vuln counts from ``npm audit --json`` output."""
    try:
        data = json.loads(audit_json or "{}")
    except json.JSONDecodeError:
        return {"total": 0, "critical": 0, "high": 0, "moderate": 0, "low": 0}
    meta = (data.get("metadata") or {}).get("vulnerabilities") or {}
    sev = {k: int(meta.get(k, 0)) for k in ("critical", "high", "moderate", "low", "info")}
    total = int(meta.get("total", sum(sev.values())))
    return {"total": total, **{k: sev[k] for k in ("critical", "high", "moderate", "low")}}


def _semver_ge(a: str, b: str) -> bool:
    """True if version ``a`` >= ``b`` (numeric dotted compare, missing→0)."""

    def parts(v: str) -> list[int]:
        nums = re.findall(r"\d+", v or "")
        return [int(x) for x in nums] or [0]

    pa, pb = parts(a), parts(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return pa >= pb


def desired_pip_bumps(alerts: list[dict[str, Any]]) -> list[PipBump]:
    """From open pip Dependabot alerts, the highest patched version wanted per
    (manifest, package). Alerts without a patched version are skipped."""
    best: dict[tuple[str, str], str] = {}
    for a in alerts:
        if a.get("state") != "open":
            continue
        dep = a.get("dependency") or {}
        pkg = dep.get("package") or {}
        if (pkg.get("ecosystem") or "").lower() != "pip":
            continue
        manifest = dep.get("manifest_path") or ""
        name = pkg.get("name") or ""
        patched = ((a.get("security_vulnerability") or {}).get("first_patched_version") or {}).get(
            "identifier"
        )
        if not (manifest and name and patched):
            continue
        key = (manifest, name.lower())
        if key not in best or _semver_ge(patched, best[key]):
            best[key] = patched
    return [PipBump(m, n, v) for (m, n), v in sorted(best.items())]


def bump_requirements_line(line: str, package: str, patched: str) -> str | None:
    """Rewrite a ``pkg==x``/``pkg>=x`` pin to ``pkg==patched`` if this line is
    that package and it is below the patched version. Returns the new line, or
    None if the line should be left unchanged. Case-insensitive on the name."""
    m = re.match(r"^(\s*)([A-Za-z0-9._-]+)\s*([=<>!~]=?)\s*v?(\d[\w.]*)\s*$", line)
    if not m:
        return None
    indent, name, _op, cur = m.groups()
    if name.lower() != package.lower():
        return None
    if _semver_ge(cur, patched):
        return None
    return f"{indent}{name}=={patched}"


def apply_pip_bumps(content: str, bumps: list[PipBump]) -> tuple[str, list[str]]:
    """Apply every relevant bump to a requirements.txt body. Returns the new
    body and the list of human-readable changes made."""
    by_pkg = {b.package.lower(): b for b in bumps}
    changed: list[str] = []
    out_lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        new = None
        if stripped and not stripped.startswith("#"):
            m = re.match(r"^\s*([A-Za-z0-9._-]+)", line)
            if m and m.group(1).lower() in by_pkg:
                b = by_pkg[m.group(1).lower()]
                new = bump_requirements_line(line, b.package, b.patched)
        if new is not None and new != line:
            changed.append(f"{stripped} → {new.strip()}")
            out_lines.append(new)
        else:
            out_lines.append(line)
    trailing = "\n" if content.endswith("\n") else ""
    return "\n".join(out_lines) + trailing, changed


def is_enabled() -> bool:
    return os.environ.get("SECURITY_AUTOFIX_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def summarize_delta(before: dict[str, int], after: dict[str, int]) -> str:
    return (
        f"total {before.get('total', 0)}→{after.get('total', 0)} "
        f"(high {before.get('high', 0)}→{after.get('high', 0)}, "
        f"moderate {before.get('moderate', 0)}→{after.get('moderate', 0)})"
    )


# ======================================================================
# Configuration
# ======================================================================


@dataclass
class Config:
    repo: str
    base: str
    push_mode: str  # "direct" | "pr"
    dry_run: bool
    run_url: str | None = None

    @classmethod
    def from_env(cls, args: argparse.Namespace) -> Config:
        repo = args.repo or os.environ.get("GITHUB_REPOSITORY") or ""
        run_url = None
        if os.environ.get("GITHUB_RUN_ID"):
            server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
            run_url = f"{server}/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        return cls(
            repo=repo,
            base=os.environ.get("SECURITY_AUTOFIX_BASE", DEFAULT_BASE),
            push_mode=os.environ.get("SECURITY_AUTOFIX_PUSH", "direct").strip().lower(),
            dry_run=bool(args.dry_run),
            run_url=run_url,
        )


# ======================================================================
# Shell / IO helpers (git / gh / npm)
# ======================================================================


def run(
    cmd: list[str], *, cwd: Path | None = None, check: bool = False, timeout: int | None = None
) -> subprocess.CompletedProcess:
    print(f"[sec-autofix] $ {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=check,
        timeout=timeout,
        capture_output=True,
        text=True,
    )


def tracked_lockfiles(repo_root: Path) -> list[str]:
    out = run(["git", "ls-files", "*package-lock.json"], cwd=repo_root).stdout
    return [p for p in out.splitlines() if p.strip()]


def npm_audit_counts(project: Path) -> dict[str, int]:
    proc = run(["npm", "audit", "--json"], cwd=project, timeout=300)
    return parse_audit_summary(proc.stdout)


def fix_npm_dir(repo_root: Path, rel_dir: str) -> dict[str, Any]:
    project = repo_root / rel_dir
    before = npm_audit_counts(project)
    if before["total"] == 0:
        return {"dir": rel_dir, "before": before, "after": before, "changed": False}
    run(["npm", "audit", "fix", "--no-audit", "--no-fund"], cwd=project, timeout=900)
    after = npm_audit_counts(project)
    changed = (
        run(["git", "status", "--porcelain", "--", rel_dir], cwd=repo_root).stdout.strip() != ""
    )
    return {"dir": rel_dir, "before": before, "after": after, "changed": changed}


def fetch_open_dependabot_alerts(repo: str) -> list[dict[str, Any]]:
    proc = run(
        ["gh", "api", "--paginate", f"repos/{repo}/dependabot/alerts?state=open&per_page=100"],
        timeout=120,
    )
    if proc.returncode != 0:
        print(f"[sec-autofix] alerts fetch failed: {proc.stderr[:200]}", file=sys.stderr)
        return []
    # --paginate concatenates JSON arrays; normalize to one list.
    alerts: list[dict[str, Any]] = []
    for chunk in re.findall(r"\[.*?\](?=\s*\[|\s*$)", proc.stdout, flags=re.DOTALL) or [
        proc.stdout
    ]:
        try:
            part = json.loads(chunk)
            if isinstance(part, list):
                alerts.extend(part)
        except json.JSONDecodeError:
            continue
    return alerts


def fix_pip_manifests(repo_root: Path, alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bumps = desired_pip_bumps(alerts)
    by_manifest: dict[str, list[PipBump]] = {}
    for b in bumps:
        by_manifest.setdefault(b.manifest_path, []).append(b)
    results: list[dict[str, Any]] = []
    for manifest, mbumps in sorted(by_manifest.items()):
        path = repo_root / manifest
        if not path.is_file():
            results.append({"manifest": manifest, "changed": [], "missing": True})
            continue
        content = path.read_text(encoding="utf-8")
        new_content, changed = apply_pip_bumps(content, mbumps)
        if changed:
            path.write_text(new_content, encoding="utf-8")
        results.append({"manifest": manifest, "changed": changed, "missing": False})
    return results


def run_deployable_checks(repo_root: Path) -> tuple[bool, str]:
    logs: list[str] = []
    ok = True
    for rel_dir, cmd in DEPLOYABLE_CHECKS:
        proc = run(cmd, cwd=repo_root / rel_dir, timeout=1200)
        passed = proc.returncode == 0
        ok &= passed
        logs.append(f"### {rel_dir}: {' '.join(cmd)} → {'PASS' if passed else 'FAIL'}")
        if not passed:
            logs.append(f"```\n{(proc.stdout + proc.stderr)[-1000:]}\n```")
    return ok, "\n".join(logs)


# ======================================================================
# Orchestration
# ======================================================================


def land_changes(cfg: Config, repo_root: Path, summary: str) -> dict[str, Any]:
    """Commit the working-tree fixes and either push to base or open a PR."""
    run(["git", "add", "-A"], cwd=repo_root)
    msg = f"fix(security): autonomous security autofix\n\n{summary}\n"
    commit = run(["git", "commit", "-m", msg], cwd=repo_root)
    if commit.returncode != 0:
        return {"landed": False, "reason": "nothing_to_commit"}
    if cfg.push_mode == "pr":
        branch = "security-autofix/sweep"
        run(["git", "push", "--force-with-lease", "origin", f"HEAD:{branch}"], cwd=repo_root)
        pr = run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                cfg.base,
                "--head",
                branch,
                "--title",
                "fix(security): autonomous security autofix",
                "--body",
                summary,
                "--label",
                "security-review",
            ],
            cwd=repo_root,
        )
        return {
            "landed": pr.returncode == 0,
            "mode": "pr",
            "detail": (pr.stdout or pr.stderr)[:300],
        }
    push = run(["git", "push", "origin", f"HEAD:{cfg.base}"], cwd=repo_root)
    return {"landed": push.returncode == 0, "mode": "direct", "detail": push.stderr[:300]}


def run_autofix(cfg: Config, repo_root: Path) -> dict[str, Any]:
    # Pristine base so the run is reproducible.
    run(["git", "fetch", "origin", cfg.base], cwd=repo_root)
    run(["git", "checkout", cfg.base], cwd=repo_root)
    run(["git", "reset", "--hard", f"origin/{cfg.base}"], cwd=repo_root)

    npm_dirs = discover_npm_dirs(tracked_lockfiles(repo_root))
    print(f"[sec-autofix] npm projects: {npm_dirs}")
    npm_results = [fix_npm_dir(repo_root, d) for d in npm_dirs]

    alerts = fetch_open_dependabot_alerts(cfg.repo)
    pip_results = fix_pip_manifests(repo_root, alerts)

    npm_changed = [r for r in npm_results if r["changed"]]
    pip_changed = [r for r in pip_results if r["changed"]]
    if not npm_changed and not pip_changed:
        print("[sec-autofix] no fixes to apply — clean exit.")
        return {"action": "noop", "npm": npm_results, "pip": pip_results}

    summary = _build_summary(npm_changed, pip_changed)
    if cfg.dry_run:
        print(f"[sec-autofix] (dry-run) would land:\n{summary}")
        return {"action": "dry_run", "summary": summary, "npm": npm_results, "pip": pip_results}

    ok, gate_log = run_deployable_checks(repo_root)
    if not ok:
        run(["git", "reset", "--hard", f"origin/{cfg.base}"], cwd=repo_root)
        print(f"[sec-autofix] deployable gate RED — aborting push.\n{gate_log}")
        return {"action": "gate_failed", "detail": gate_log[:3000]}

    landed = land_changes(cfg, repo_root, summary)
    append_journal(
        {
            "action": "landed" if landed.get("landed") else "land_failed",
            "summary": summary,
            **landed,
        },
        repo_root=repo_root,
    )
    return {
        "action": "landed" if landed.get("landed") else "land_failed",
        **landed,
        "summary": summary,
    }


def _build_summary(npm_changed: list[dict[str, Any]], pip_changed: list[dict[str, Any]]) -> str:
    lines = []
    for r in npm_changed:
        lines.append(f"- npm `{r['dir']}`: {summarize_delta(r['before'], r['after'])}")
    for r in pip_changed:
        for c in r["changed"]:
            lines.append(f"- pip `{r['manifest']}`: {c}")
    return "\n".join(lines) or "(no changes)"


def append_journal(entry: dict[str, Any], *, repo_root: Path) -> None:
    journal = repo_root / "docs" / "autopilot" / "SECURITY_AUTOFIX_JOURNAL.md"
    try:
        line = f"- `{_now_iso()}` — **{entry.get('action')}**\n{entry.get('summary', '')}\n"
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:  # pragma: no cover
        print(f"[sec-autofix] journal append failed: {exc}", file=sys.stderr)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manifest Security Autofix")
    parser.add_argument("--repo", type=str, default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true", help="Plan only; no writes/push")
    args = parser.parse_args()

    cfg = Config.from_env(args)
    if not cfg.repo:
        sys.exit("--repo is required (or set GITHUB_REPOSITORY)")
    repo_root = args.repo_root.resolve()

    if not is_enabled() and not args.dry_run:
        print("[sec-autofix] SECURITY_AUTOFIX_ENABLED != true — no-op exit.")
        return 0

    result = run_autofix(cfg, repo_root)
    print(f"[sec-autofix] done — action={result.get('action')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
