"""Manifest PR Merge Train — autonomous "merge every open PR into main" loop.

This is the deterministic sibling of the Autopilot loop. Where Autopilot
(``run_autopilot_agent.py``) fixes *issues* with an LLM and deliberately
**never touches `main`**, the Merge Train does the one thing Autopilot won't:
it sweeps every open pull request into ``main``, resolves the conflicts it can
safely resolve, runs the same checks ``scripts/check.py`` runs, pushes, and deletes the
merged branch. Each push to ``main`` auto-releases — that is intentional and
human-authorized (see docs/AUTOPILOT.md → "PR Merge Train").

It carries no model and no budget gate because it spends nothing: every step is
plain ``git`` / ``gh`` / ``npm`` / ``pytest``. The only knob is the kill switch.

One run does, for each open PR (safest first):

  1. Kill switch (fail-closed). If ``PR_MERGE_TRAIN_ENABLED`` != "true", no-op.
  2. Merge the PR head into a local ``main``.
       - Clean merge                         → keep.
       - Conflicts only in regenerable lock  → regenerate the lockfile, keep.
         files (``package-lock.json``)
       - Any other conflict (code/manifest)  → abort, comment, SKIP (human).
  3. Run the same gate ``scripts/check.py`` runs, scoped to what changed
     (ruff/pytest for backend, ``npm ci`` + test + build for frontend).
       - green → keep the merge.
       - red   → reset the merge out of ``main``, comment, SKIP.
  4. After all merges, push ``main`` once and delete every merged branch
     **except the protected ones** (``main``, ``autopilot``).

Robustness over coverage: a PR the train cannot land cleanly-and-green is left
exactly as it was, with a comment, for a human — ``main`` never receives a red
or hand-guessed merge. Expected failures exit 0 (no cron error-spam); only an
unexpected crash exits non-zero.

The *decision* logic (ordering, conflict classification, branch-protection
guard) is pure and unit-tested without git or the network — see
``backend/tests/test_pr_merge_train.py``.

Required env (provided by the GHA workflow):
  GITHUB_TOKEN         — ``gh`` auth + push token
  GITHUB_REPOSITORY    — owner/repo
Optional env (repo variables, all have safe defaults):
  PR_MERGE_TRAIN_ENABLED   — must be "true" to act; anything else = no-op
  PR_MERGE_TRAIN_PROTECTED — comma list of never-deleted branches
                             (default "main,autopilot")
  PR_MERGE_TRAIN_BASE      — branch to merge into (default "main")
  PR_MERGE_TRAIN_INCLUDE_DRAFTS — "true" to include draft PRs (default false)
  PR_MERGE_TRAIN_RUN_CHECKS     — "false" to skip the local CI gate (default true)

Usage:
  python backend/scripts/run_pr_merge_train.py            # sweep all open PRs
  python backend/scripts/run_pr_merge_train.py --dry-run  # plan only, no writes
  python backend/scripts/run_pr_merge_train.py --pr 262    # only that PR
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BASE = "main"
DEFAULT_PROTECTED = ("main", "autopilot")

# Lockfiles the train may regenerate to resolve a conflict. Anything NOT in
# this set, when conflicted, makes the merge "code" (left for a human).
REGENERABLE_LOCKFILES = ("frontend/package-lock.json",)


# ======================================================================
# Pure decision logic (no git, no network) — unit-tested directly.
# ======================================================================


@dataclass
class PullRequest:
    number: int
    title: str
    head_ref: str
    base_ref: str
    is_draft: bool
    is_dependabot: bool
    update_type: str = ""  # "major" | "minor" | "patch" | "" (non-dep)

    @classmethod
    def from_gh(cls, data: dict[str, Any]) -> PullRequest:
        author = ((data.get("author") or {}).get("login") or "").lower()
        return cls(
            number=int(data.get("number") or 0),
            title=str(data.get("title") or ""),
            head_ref=str(data.get("headRefName") or ""),
            base_ref=str(data.get("baseRefName") or ""),
            is_draft=bool(data.get("isDraft")),
            is_dependabot="dependabot" in author,
        )


def normalize_protected(raw: str | None) -> set[str]:
    """Parse the protected-branch list; ``main`` is *always* protected."""
    names = {p.strip() for p in (raw or "").split(",") if p.strip()}
    names |= set(DEFAULT_PROTECTED)
    names.add("main")
    return names


def is_protected_branch(name: str, protected: set[str]) -> bool:
    return (name or "").strip() in protected


def should_delete_branch(branch: str, *, protected: set[str]) -> bool:
    """A branch may be deleted only if it is non-empty and not protected."""
    b = (branch or "").strip()
    return bool(b) and not is_protected_branch(b, protected)


def eligible_prs(prs: list[PullRequest], *, base: str, include_drafts: bool) -> list[PullRequest]:
    """Open PRs targeting ``base`` that the train should attempt."""
    return [
        p for p in prs if p.base_ref == base and p.number > 0 and (include_drafts or not p.is_draft)
    ]


def _risk_rank(pr: PullRequest) -> int:
    """Lower = safer = merged earlier. Dependabot patch/minor first, then
    other dependency bumps, then everything else (human-authored last)."""
    if pr.is_dependabot and pr.update_type in {"patch", "minor"}:
        return 0
    if pr.is_dependabot:
        return 1
    return 2


def merge_order(prs: list[PullRequest]) -> list[PullRequest]:
    """Safest PRs first; ties broken by ascending PR number (oldest first)."""
    return sorted(prs, key=lambda p: (_risk_rank(p), p.number))


def classify_conflict(
    conflicted_paths: list[str], *, regenerable: tuple[str, ...] = REGENERABLE_LOCKFILES
) -> str:
    """Classify a set of conflicted paths.

    Returns ``"clean"`` (no conflicts), ``"lockfile_only"`` (every conflict is
    a regenerable lockfile — the train can fix it), or ``"code"`` (at least one
    real conflict — leave it for a human).
    """
    paths = [p.strip() for p in conflicted_paths if p.strip()]
    if not paths:
        return "clean"
    patterns = set(regenerable)
    if all(p in patterns or any(fnmatch.fnmatch(p, pat) for pat in patterns) for p in paths):
        return "lockfile_only"
    return "code"


def lockfile_dirs(conflicted_lockfiles: list[str]) -> list[str]:
    """The npm project dirs (parent of each conflicted lockfile) to reinstall."""
    out: list[str] = []
    for p in conflicted_lockfiles:
        d = str(Path(p).parent)
        if d not in out:
            out.append(d)
    return out


# ======================================================================
# Configuration
# ======================================================================


@dataclass
class Config:
    repo: str
    base: str
    protected: set[str]
    include_drafts: bool
    run_checks: bool
    dry_run: bool
    only_pr: int | None
    server_url: str
    run_url: str | None = field(default=None)

    @classmethod
    def from_env(cls, args: argparse.Namespace) -> Config:
        repo = args.repo or os.environ.get("GITHUB_REPOSITORY") or ""
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        run_url = None
        if os.environ.get("GITHUB_RUN_ID"):
            run_url = f"{server}/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        return cls(
            repo=repo,
            base=os.environ.get("PR_MERGE_TRAIN_BASE", DEFAULT_BASE),
            protected=normalize_protected(os.environ.get("PR_MERGE_TRAIN_PROTECTED")),
            include_drafts=_env_bool("PR_MERGE_TRAIN_INCLUDE_DRAFTS", default=False),
            run_checks=_env_bool("PR_MERGE_TRAIN_RUN_CHECKS", default=True),
            dry_run=bool(args.dry_run),
            only_pr=args.pr,
            server_url=server,
            run_url=run_url,
        )


def _env_bool(name: str, *, default: bool) -> bool:
    return os.environ.get(name, "true" if default else "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def merge_train_enabled() -> bool:
    return os.environ.get("PR_MERGE_TRAIN_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# ======================================================================
# Shell helpers (git / gh / npm)
# ======================================================================


def run(
    cmd: list[str], *, cwd: Path | None = None, check: bool = True, timeout: int | None = None
) -> subprocess.CompletedProcess:
    print(f"[merge-train] $ {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=check,
        timeout=timeout,
        capture_output=True,
        text=True,
    )


def list_open_prs(repo: str) -> list[PullRequest]:
    proc = run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--limit",
            "200",
            "--json",
            "number,title,headRefName,baseRefName,isDraft,author",
        ]
    )
    data = json.loads(proc.stdout or "[]")
    prs = [PullRequest.from_gh(d) for d in data]
    for pr in prs:
        if pr.is_dependabot:
            pr.update_type = dependabot_update_type(repo, pr.number)
    return prs


def dependabot_update_type(repo: str, number: int) -> str:
    """Best-effort semver bump class from the Dependabot PR title.

    Avoids an extra API call: Dependabot titles read 'Bump X from a.b.c to
    d.e.f'. We compare the leading version components.
    """
    proc = run(
        ["gh", "pr", "view", str(number), "--repo", repo, "--json", "title"],
        check=False,
    )
    try:
        title = json.loads(proc.stdout or "{}").get("title", "")
    except json.JSONDecodeError:
        return ""
    return _semver_bump_from_title(title)


def _semver_bump_from_title(title: str) -> str:
    import re

    m = re.search(r"from\s+v?(\d+)\.(\d+)\.(\d+)\s+to\s+v?(\d+)\.(\d+)\.(\d+)", title or "")
    if not m:
        return ""
    a = tuple(int(x) for x in m.group(1, 2, 3))
    b = tuple(int(x) for x in m.group(4, 5, 6))
    if b[0] != a[0]:
        return "major"
    if b[1] != a[1]:
        return "minor"
    return "patch"


def conflicted_files(repo_root: Path) -> list[str]:
    out = run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=repo_root, check=False).stdout
    return [p.strip() for p in out.splitlines() if p.strip()]


def regenerate_lockfiles(repo_root: Path, conflicted: list[str]) -> bool:
    """Resolve lockfile conflicts by reinstalling each affected npm project."""
    ok = True
    for d in lockfile_dirs(conflicted):
        proj = repo_root / d
        # Take the merged package.json (`theirs` already merged by ort where
        # possible); regenerate the lockfile to match it.
        run(
            ["git", "checkout", "--theirs", "--", d + "/package-lock.json"],
            cwd=repo_root,
            check=False,
        )
        proc = run(
            ["npm", "install", "--no-audit", "--no-fund", "--package-lock-only"],
            cwd=proj,
            check=False,
            timeout=600,
        )
        if proc.returncode != 0:
            print(
                f"[merge-train] lockfile regen failed in {d}: {proc.stderr[-300:]}", file=sys.stderr
            )
            ok = False
        run(
            ["git", "add", "--", d + "/package-lock.json", d + "/package.json"],
            cwd=repo_root,
            check=False,
        )
    return ok


def run_repo_checks(repo_root: Path, *, changed_paths: list[str]) -> tuple[bool, str]:
    """The same gate scripts/check.py runs, scoped to what changed."""
    touched_backend = any(p.startswith(("backend/", "mcp_server/")) for p in changed_paths)
    touched_frontend = any(p.startswith("frontend/") for p in changed_paths)
    logs: list[str] = []

    def _step(name: str, cmd: list[str], cwd: Path) -> bool:
        proc = run(cmd, cwd=cwd, check=False, timeout=1200)
        ok = proc.returncode == 0
        logs.append(
            f"### {name}: {'PASS' if ok else 'FAIL'}\n```\n{(proc.stdout + proc.stderr)[-1200:]}\n```"
        )
        return ok

    ok = True
    if touched_backend:
        ok &= _step("ruff", ["ruff", "check", "backend/app", "mcp_server/src"], repo_root)
        ok &= _step("pytest", ["python", "-m", "pytest", "tests", "-q"], repo_root / "backend")
    if touched_frontend:
        ok &= _step("npm ci", ["npm", "ci", "--no-audit", "--no-fund"], repo_root / "frontend")
        ok &= _step("jest", ["npm", "test", "--", "--watchAll=false"], repo_root / "frontend")
        ok &= _step("build", ["npm", "run", "build"], repo_root / "frontend")
    return ok, "\n\n".join(logs)


def gh_comment(repo: str, number: int, body: str) -> None:
    run(["gh", "pr", "comment", str(number), "--repo", repo, "--body", body], check=False)


# ======================================================================
# Orchestration
# ======================================================================


def merge_one(*, cfg: Config, pr: PullRequest, repo_root: Path) -> dict[str, Any]:
    """Attempt to land a single PR onto the local base branch.

    Returns an outcome dict; the base branch is left advanced only on
    ``action == "merged"``. Any other outcome leaves the base untouched.
    """
    run(["git", "fetch", "origin", f"pull/{pr.number}/head"], cwd=repo_root, check=False)
    head = "FETCH_HEAD"
    merge = run(
        ["git", "merge", "--no-ff", "-m", f"Merge PR #{pr.number} into {cfg.base}", head],
        cwd=repo_root,
        check=False,
    )
    if merge.returncode == 0:
        kind = "clean"
    else:
        conflicts = conflicted_files(repo_root)
        kind = classify_conflict(conflicts)
        if kind == "code":
            run(["git", "merge", "--abort"], cwd=repo_root, check=False)
            return {"action": "skipped_conflict", "number": pr.number, "detail": conflicts}
        if kind == "lockfile_only":
            if not regenerate_lockfiles(repo_root, conflicts):
                run(["git", "merge", "--abort"], cwd=repo_root, check=False)
                return {"action": "skipped_lockfile_regen_failed", "number": pr.number}
            commit = run(["git", "commit", "--no-edit"], cwd=repo_root, check=False)
            if commit.returncode != 0:
                run(["git", "merge", "--abort"], cwd=repo_root, check=False)
                return {"action": "skipped_commit_failed", "number": pr.number}

    # Validate the same way scripts/check.py does, then keep or back out.
    if cfg.run_checks:
        changed = run(
            ["git", "diff", "--name-only", f"origin/{cfg.base}...HEAD"], cwd=repo_root, check=False
        ).stdout.splitlines()
        ok, log = run_repo_checks(
            repo_root, changed_paths=[c.strip() for c in changed if c.strip()]
        )
        if not ok:
            # Reset the just-made merge commit out of the base branch.
            run(["git", "reset", "--hard", f"origin/{cfg.base}"], cwd=repo_root, check=False)
            return {"action": "skipped_red_checks", "number": pr.number, "detail": log[:3000]}

    return {"action": "merged", "number": pr.number, "head_ref": pr.head_ref, "resolution": kind}


def run_train(cfg: Config, repo_root: Path) -> dict[str, Any]:
    prs = list_open_prs(cfg.repo)
    if cfg.only_pr:
        prs = [p for p in prs if p.number == cfg.only_pr]
    todo = merge_order(eligible_prs(prs, base=cfg.base, include_drafts=cfg.include_drafts))
    print(f"[merge-train] {len(todo)} eligible PR(s): {[p.number for p in todo]}")

    # Start from a pristine base so the train is reproducible.
    run(["git", "fetch", "origin", cfg.base], cwd=repo_root)
    run(["git", "checkout", cfg.base], cwd=repo_root, check=False)
    run(["git", "reset", "--hard", f"origin/{cfg.base}"], cwd=repo_root, check=False)

    merged: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for pr in todo:
        print(f"[merge-train] === PR #{pr.number}: {pr.title} ===")
        outcome = merge_one(cfg=cfg, pr=pr, repo_root=repo_root)
        (merged if outcome["action"] == "merged" else skipped).append(outcome)
        if outcome["action"] != "merged" and not cfg.dry_run:
            gh_comment(
                cfg.repo,
                pr.number,
                _skip_comment(outcome, cfg.run_url),
            )

    pushed = False
    if merged and not cfg.dry_run:
        push = run(["git", "push", "origin", cfg.base], cwd=repo_root, check=False)
        pushed = push.returncode == 0
        if not pushed:
            print(f"[merge-train] push failed: {push.stderr[-300:]}", file=sys.stderr)

    deleted = delete_merged_branches(cfg, merged, repo_root, pushed=pushed)

    append_journal(
        {
            "merged": [m["number"] for m in merged],
            "skipped": [s["number"] for s in skipped],
            "deleted": deleted,
            "pushed": pushed,
        },
        repo_root=repo_root,
    )
    return {"merged": merged, "skipped": skipped, "deleted": deleted, "pushed": pushed}


def delete_merged_branches(
    cfg: Config, merged: list[dict[str, Any]], repo_root: Path, *, pushed: bool
) -> list[str]:
    """Delete each merged PR's head branch — never a protected one."""
    deleted: list[str] = []
    if cfg.dry_run or not pushed:
        return deleted
    for m in merged:
        branch = m.get("head_ref", "")
        if not should_delete_branch(branch, protected=cfg.protected):
            if branch:
                print(f"[merge-train] keeping protected/empty branch: {branch!r}")
            continue
        res = run(["git", "push", "origin", "--delete", branch], cwd=repo_root, check=False)
        if res.returncode == 0:
            deleted.append(branch)
    return deleted


def _skip_comment(outcome: dict[str, Any], run_url: str | None) -> str:
    reasons = {
        "skipped_conflict": "this PR has a **non-lockfile merge conflict** with `main` that needs a human to resolve.",
        "skipped_lockfile_regen_failed": "the lockfile could not be regenerated automatically.",
        "skipped_commit_failed": "the resolved merge could not be committed.",
        "skipped_red_checks": "the merge made CI **red**, so it was backed out of `main`.",
    }
    why = reasons.get(outcome["action"], outcome["action"])
    tail = (
        f"\n\n<details><summary>details</summary>\n\n```\n{outcome.get('detail')}\n```\n</details>"
        if outcome.get("detail")
        else ""
    )
    ci = f"\n\n_Merge Train run: {run_url}_" if run_url else ""
    return f"🚆 **Manifest PR Merge Train** skipped this PR: {why}{tail}{ci}"


def append_journal(entry: dict[str, Any], *, repo_root: Path) -> None:
    journal = repo_root / "docs" / "autopilot" / "MERGE_TRAIN_JOURNAL.md"
    try:
        line = (
            f"- `{_now_iso()}` — merged {entry.get('merged')} · "
            f"skipped {entry.get('skipped')} · deleted {entry.get('deleted')} · "
            f"pushed={entry.get('pushed')}\n"
        )
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:  # pragma: no cover
        print(f"[merge-train] journal append failed: {exc}", file=sys.stderr)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manifest PR Merge Train")
    parser.add_argument("--repo", type=str, default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--pr", type=int, default=None, help="Only operate on this PR number")
    parser.add_argument(
        "--dry-run", action="store_true", help="Plan only; no merges/pushes/deletes"
    )
    args = parser.parse_args()

    cfg = Config.from_env(args)
    if not cfg.repo:
        sys.exit("--repo is required (or set GITHUB_REPOSITORY)")
    repo_root = args.repo_root.resolve()

    if not merge_train_enabled() and not args.dry_run:
        print("[merge-train] PR_MERGE_TRAIN_ENABLED != true — no-op exit.")
        return 0

    result = run_train(cfg, repo_root)
    print(
        f"[merge-train] done — merged={[m['number'] for m in result['merged']]} "
        f"skipped={[s['number'] for s in result['skipped']]} "
        f"deleted={result['deleted']} pushed={result['pushed']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
