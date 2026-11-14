"""Manifest Autopilot — autonomous self-improvement runner (v2 of the agent loop).

Invoked by ``.github/workflows/autopilot.yml`` on an hourly cron. Where the
v1 bug-fix agent (``run_bugfix_agent.py``) is *diagnose-only*, autopilot
closes the loop: it actually writes the change, verifies it, and opens an
auto-merging PR — but never against ``main`` (which auto-releases on every
push). It targets a protected ``autopilot`` branch that a human promotes to
``main`` on their own cadence.

One cron run does exactly one unit of work:

  1. Kill switch + budget gate (fail-closed). If autopilot is disabled, or
     today's spend is already at/over the daily cap, exit 0 as a no-op.
  2. Select one issue. Pull open GitHub issues, keep the ones labelled for
     autopilot, drop any that already have an open autopilot PR, and rank.
  3. Implement on an isolated worktree branch using the **OpenAI Codex CLI**
     in headless mode (``codex exec``) — an agentic coding CLI driven by the
     org's OpenAI key. Codex reads ``AGENTS.md`` natively for repo
     conventions; the denylist, diff-size, and CI guards below are what keep
     it inside the safe envelope.
  4. Guardrails (fail-closed): the diff may not touch the denylist (the
     loop's own safety rails) and may not exceed the size cap; then run the
     same checks ``scripts/check.py`` runs.
  5. Open an auto-merging PR into the ``autopilot`` branch.
  6. Record spend into the cost ledger (``agent_cost_events``) so the budget
     gate sees it next run, and append a line to the journal.

The runner is deliberately resilient: any expected failure (no work, red
checks, oversized diff, engine error) posts a comment, records the attempt,
and exits 0 so the cron does not error-spam. Only an unexpected crash exits
non-zero.

The *decision* logic (budget, denylist, diff size, ranking, prompt) lives in
pure functions at the top so it is unit-tested without a DB, a network, or a
real engine run — see ``backend/tests/test_autopilot_budget_gate.py``.

Required env (provided by the GHA workflow):
  GITHUB_TOKEN               — GitHub API token + ``gh`` auth (workflow-provided)
  GITHUB_REPOSITORY          — owner/repo (workflow-provided)
  GITHUB_RUN_ID / _SERVER_URL — for the ci_run_url link (workflow-provided)
  OPENAI_API_KEY             — Codex CLI engine (wired from the org OPENAI_DEV_KEY)
  DATABASE_URL               — cost ledger (budget gate). Absent → fail-closed.
Optional env (repo variables, all have safe defaults):
  AUTOPILOT_ENABLED          — must be "true" to run; anything else = no-op
  AUTOPILOT_DAILY_USD        — daily model-cost cap (default 30)
  AUTOPILOT_PER_RUN_USD      — advisory per-run ceiling passed to the engine (default 3)
  AUTOPILOT_MODEL            — default coding model (default gpt-5-codex)
  AUTOPILOT_BASE_BRANCH      — PR base, never main (default "autopilot")
  AUTOPILOT_MAX_FILES        — diff size guard (default 12)
  AUTOPILOT_MAX_LINES        — diff size guard (default 600)
  AUTOPILOT_REPAIR_ATTEMPTS  — CI-failure fix-and-retry rounds before giving up (default 2)
  AUTOPILOT_AUTOMERGE        — "true" to enable `gh pr merge --auto` (default false)

Usage:
  python backend/scripts/run_autopilot_agent.py            # pick + do one issue
  python backend/scripts/run_autopilot_agent.py --issue-number 42
  python backend/scripts/run_autopilot_agent.py --dry-run  # plan only, no PR
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

AGENT_KIND = "autopilot"
# Synthetic identity the loop spends under, so its events are isolated from
# real users in the shared agent_cost_events ledger.
SYSTEM_USER_ID = "autopilot-system"

DEFAULT_DAILY_CAP_USD = 30.0
DEFAULT_PER_RUN_CAP_USD = 3.0
# OpenAI Codex CLI models. gpt-5-codex is Codex's purpose-built coding model;
# autopilot:hard routes to the stronger general model. NOTE: add the exact
# input/output pricing for whichever model you run to PRICING_USD_PER_1M in
# cost_tracking_service.py so the daily budget cap is precise — unknown models
# fall back to a conservative ($1/$3 per 1M) estimate.
DEFAULT_MODEL = "gpt-5-codex"
HARD_MODEL = "gpt-5"
DEFAULT_BASE_BRANCH = "autopilot"
DEFAULT_MAX_FILES = 12
DEFAULT_MAX_LINES = 600
# How many times to feed CI failures back to the engine to fix before giving
# up. The PR only opens once the change passes everything scripts/check.py runs, so
# CI errors are repaired *before* merge, not after.
DEFAULT_REPAIR_ATTEMPTS = 2

# Labels that make an issue eligible, and the escape hatches. Includes the
# labels the repo's own audit loops actually file (website-audit, accessibility,
# seo) — these are the "improvements from the actual page". Security/governance
# labels are deliberately NOT eligible: those touch denylisted, sensitive code
# and need a human.
ELIGIBLE_LABELS = {
    "automated-test",
    "autopilot",
    "feature",
    "bug",
    "enhancement",
    "website-audit",
    "accessibility",
    "seo",
}
SKIP_LABEL = "autopilot:skip"
HARD_LABEL = "autopilot:hard"

# Priority labels → rank weight (higher = picked first).
PRIORITY_WEIGHT = {
    "priority:critical": 100,
    "priority:high": 60,
    "automated-test": 40,  # a real production smoke-test failure
    "bug": 30,
    "accessibility": 25,  # small, safe, high-value page fixes
    "priority:medium": 20,
    "website-audit": 18,
    "autopilot": 15,
    "seo": 12,
    "enhancement": 10,
    "feature": 5,
}

# The loop's own safety rails. The engine is told not to touch these, AND the
# diff is rejected if it does — self-modification of the guardrails is blocked.
DENYLIST_PREFIXES = (
    ".github/workflows/",
    "backend/app/auth/",
    "backend/app/security/",
    "backend/app/config/",
    "backend/scripts/run_autopilot_agent.py",
    "backend/scripts/run_bugfix_agent.py",
    "backend/scripts/run_pr_merge_train.py",
    "backend/scripts/run_security_autofix.py",
    "docs/autopilot/",
    ".claude/skills/manifest-",
)
DENYLIST_EXACT = ("CODEOWNERS", ".github/CODEOWNERS")

ENGINE_TIMEOUT_SECONDS = int(os.environ.get("AUTOPILOT_ENGINE_TIMEOUT", "1800"))


# ======================================================================
# Pure decision logic (no DB, no network) — unit-tested directly.
# ======================================================================


def slugify(text: str, *, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (slug[:max_len].strip("-")) or "change"


def path_is_denylisted(path: str) -> bool:
    p = path or ""
    if p.startswith("./"):
        p = p[2:]
    if p in DENYLIST_EXACT:
        return True
    return any(p.startswith(prefix) for prefix in DENYLIST_PREFIXES)


def denylisted_changes(changed_paths: list[str]) -> list[str]:
    """Return the subset of changed paths that touch the loop's safety rails."""
    return [p for p in changed_paths if path_is_denylisted(p)]


def evaluate_budget(
    *, spent_today_usd: float, daily_cap_usd: float, per_run_cap_usd: float
) -> dict[str, Any]:
    """Decide whether another run may spend money right now.

    Fail-closed by construction: callers that cannot determine ``spent_today``
    must pass a value at/above the cap so this returns ``allowed=False``.
    """
    spent = max(0.0, float(spent_today_usd))
    daily = max(0.0, float(daily_cap_usd))
    remaining = round(daily - spent, 6)
    if daily <= 0:
        return {"allowed": False, "reason": "daily_cap_zero", "remaining_usd": 0.0}
    if spent >= daily:
        return {"allowed": False, "reason": "daily_cap_reached", "remaining_usd": 0.0}
    if remaining < per_run_cap_usd * 0.25:
        # Not enough headroom for even a minimal run; stop cleanly rather than
        # start work we may have to abandon mid-flight.
        return {"allowed": False, "reason": "insufficient_headroom", "remaining_usd": remaining}
    return {"allowed": True, "reason": None, "remaining_usd": remaining}


def evaluate_diff(
    *, changed_paths: list[str], insertions: int, deletions: int, max_files: int, max_lines: int
) -> dict[str, Any]:
    """Reject a change that escapes the loop's safe envelope."""
    blocked = denylisted_changes(changed_paths)
    if blocked:
        return {"ok": False, "reason": "denylisted_paths", "detail": blocked}
    if not changed_paths:
        return {"ok": False, "reason": "empty_diff", "detail": []}
    if len(changed_paths) > max_files:
        return {
            "ok": False,
            "reason": "too_many_files",
            "detail": [f"{len(changed_paths)} files > limit {max_files}"],
        }
    total_lines = int(insertions) + int(deletions)
    if total_lines > max_lines:
        return {
            "ok": False,
            "reason": "diff_too_large",
            "detail": [f"{total_lines} changed lines > limit {max_lines}"],
        }
    return {"ok": True, "reason": None, "detail": []}


def issue_rank(issue: Issue) -> tuple[int, int]:
    """Higher weight first; for ties, older issue (lower number) first."""
    weight = max((PRIORITY_WEIGHT.get(lbl, 0) for lbl in issue.labels), default=0)
    return (weight, -issue.number)


def select_issue(issues: list[Issue], *, busy_issue_numbers: set[int]) -> Issue | None:
    """Pick the single highest-value eligible issue not already in flight."""
    candidates = [
        i
        for i in issues
        if not i.is_pull_request
        and i.number not in busy_issue_numbers
        and SKIP_LABEL not in i.labels
        and (ELIGIBLE_LABELS & set(i.labels))
    ]
    if not candidates:
        return None
    return sorted(candidates, key=issue_rank, reverse=True)[0]


def model_for_issue(issue: Issue, *, default_model: str) -> str:
    return HARD_MODEL if HARD_LABEL in issue.labels else default_model


def build_implementation_prompt(
    *, issue: Issue, base_branch: str, per_run_cap_usd: float, max_files: int, max_lines: int
) -> str:
    """The scoped brief the Codex engine runs against, inside the worktree."""
    denylist = "\n".join(f"  - {p}" for p in (*DENYLIST_PREFIXES, *DENYLIST_EXACT))
    return f"""You are Manifest Autopilot, an autonomous engineer improving this repository.

Implement a focused, production-quality change that resolves GitHub issue
#{issue.number}: "{issue.title}".

ISSUE BODY:
{issue.body[:6000]}

NON-NEGOTIABLE RULES:
- First read AGENTS.md, CLAUDE.md and docs/AI_AGENT_BASE_PROMPT.md and obey them.
  They define this repo's file-ownership, docs-sync, AI-cost and guest-session
  rules — follow them exactly.
- Make the SMALLEST change that fully resolves the issue. Hard limits: at most
  {max_files} files and {max_lines} changed lines. If the issue cannot be done
  within that envelope, do NOT hack around it — write a short note to stdout
  starting with "AUTOPILOT_DECLINE:" explaining why, and make no changes.
- Add or update proportionate tests, and update docs/ if a public contract
  (GraphQL schema, REST route, MCP contract, env var, CLI) changes.
- You MUST NOT modify any of these protected paths (the loop's own safety
  rails) — touching them will cause the whole change to be discarded:
{denylist}
- Keep cost low: this run's budget is ~${per_run_cap_usd:.2f}. Make the
  tightest change that works and avoid unnecessary exploration.
- Run the relevant tests yourself (pytest for backend, `npm test` for frontend)
  and iterate until they pass before you finish.
- Do NOT commit, push, branch, or open a PR — the orchestrator does that. Just
  leave the working tree with your change in place on branch {base_branch}-work.

When done, print a one-paragraph summary of what you changed and why.
"""


def build_repair_prompt(*, issue: Issue, checks_log: str, max_files: int, max_lines: int) -> str:
    """Brief to fix a red check run, keeping the change inside the envelope.

    Fed back to the engine when the local CI-equivalent gate fails, so the PR
    only opens once the same checks scripts/check.py runs are green.
    """
    denylist = "\n".join(f"  - {p}" for p in (*DENYLIST_PREFIXES, *DENYLIST_EXACT))
    return f"""Your change for issue #{issue.number} did NOT pass the repository checks.
Fix it. These are the same checks CI runs — the change cannot merge until they
are green.

FAILING CHECK OUTPUT (ruff / pytest / jest):
{checks_log[:6000]}

RULES (unchanged):
- Keep the original fix; make the smallest additional edits needed to turn the
  checks green. Stay within {max_files} files and {max_lines} changed lines total.
- If the failure reveals the issue genuinely cannot be solved within that
  envelope, print a line starting with "AUTOPILOT_DECLINE:" and revert your
  changes (`git checkout -- .`).
- Do NOT modify these protected paths:
{denylist}
- Do NOT commit, push, branch, or open a PR — just leave the corrected working
  tree in place. Re-run the failing tests yourself to confirm they pass.

When done, print a one-line summary of what you fixed.
"""


def parse_codex_result(stdout: str) -> dict[str, Any]:
    """Extract result text + token usage from `codex exec --json` output.

    Codex emits a stream of JSONL events; the exact schema varies by version,
    so we are deliberately permissive: we walk every JSON object, keep the last
    agent/assistant message as the result text, and pick up token counts from
    whatever usage-shaped fields appear. Token counts feed the cost ledger
    (priced via cost_tracking_service), so the caller supplies an estimate when
    none are reported — the budget gate must never see a free ($0) run.
    """
    objs = _iter_json_objects(stdout)
    result_text = ""
    input_tokens = 0
    output_tokens = 0
    model: str | None = None
    is_error = False
    for obj in objs:
        text = _extract_message_text(obj)
        if text:
            result_text = text
        ti, to = _extract_token_usage(obj)
        input_tokens = max(input_tokens, ti)
        output_tokens = max(output_tokens, to)
        m = obj.get("model") or (obj.get("item") or {}).get("model")
        if isinstance(m, str) and m:
            model = m
        if obj.get("type") in {"error", "turn.failed"} or obj.get("is_error"):
            is_error = True
    return {
        "result_text": result_text.strip(),
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "model": model,
        "is_error": is_error,
        "raw": objs[-1] if objs else {},
    }


def _iter_json_objects(text: str) -> list[dict[str, Any]]:
    """All top-level JSON objects in ``text`` (JSONL or concatenated)."""
    decoder = json.JSONDecoder()
    out: list[dict[str, Any]] = []
    s = text or ""
    idx = 0
    while True:
        start = s.find("{", idx)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(s[start:])
            if isinstance(obj, dict):
                out.append(obj)
            idx = start + end
        except json.JSONDecodeError:
            idx = start + 1
    return out


def _extract_message_text(obj: dict[str, Any]) -> str:
    """Pull an agent/assistant message out of a Codex event, if present."""
    item = obj.get("item") if isinstance(obj.get("item"), dict) else {}
    for candidate in (
        item.get("text") if item.get("type") in {"agent_message", "assistant_message"} else None,
        obj.get("text") if obj.get("role") in {"assistant", "agent"} else None,
        obj.get("last_agent_message"),
        obj.get("result"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return ""


def _extract_token_usage(obj: dict[str, Any]) -> tuple[int, int]:
    """Best-effort (input, output) token counts from a usage-shaped object."""
    usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else obj
    in_keys = ("input_tokens", "prompt_tokens", "total_input_tokens")
    out_keys = ("output_tokens", "completion_tokens", "total_output_tokens")
    ti = next((int(usage[k]) for k in in_keys if isinstance(usage.get(k), int | float)), 0)
    to = next((int(usage[k]) for k in out_keys if isinstance(usage.get(k), int | float)), 0)
    return ti, to


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) for the no-usage-reported fallback."""
    return max(1, len(text or "") // 4)


def declined_from_result(result_text: str) -> str | None:
    for line in (result_text or "").splitlines():
        if line.strip().startswith("AUTOPILOT_DECLINE:"):
            return line.split("AUTOPILOT_DECLINE:", 1)[1].strip()
    return None


# ======================================================================
# Data shapes
# ======================================================================


@dataclass
class Issue:
    number: int
    title: str
    url: str
    body: str
    labels: list[str] = field(default_factory=list)
    is_pull_request: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Issue:
        return cls(
            number=int(data.get("number") or 0),
            title=str(data.get("title") or ""),
            url=str(data.get("html_url") or ""),
            body=str(data.get("body") or ""),
            labels=[str(label.get("name") or "") for label in (data.get("labels") or [])],
            is_pull_request="pull_request" in data,
        )


# ======================================================================
# Configuration
# ======================================================================


@dataclass
class Config:
    repo: str
    base_branch: str
    daily_cap_usd: float
    per_run_cap_usd: float
    default_model: str
    max_files: int
    max_lines: int
    repair_attempts: int
    automerge: bool
    dry_run: bool
    ci_run_url: str | None

    @classmethod
    def from_env(cls, args: argparse.Namespace) -> Config:
        repo = args.repo or os.environ.get("GITHUB_REPOSITORY") or ""
        ci_run_url = None
        if os.environ.get("GITHUB_SERVER_URL") and os.environ.get("GITHUB_RUN_ID"):
            ci_run_url = (
                f"{os.environ['GITHUB_SERVER_URL']}/{repo}/"
                f"actions/runs/{os.environ['GITHUB_RUN_ID']}"
            )
        return cls(
            repo=repo,
            base_branch=os.environ.get("AUTOPILOT_BASE_BRANCH", DEFAULT_BASE_BRANCH),
            daily_cap_usd=_env_float(
                "AUTOPILOT_DAILY_USD", DEFAULT_DAILY_CAP_USD, override=args.daily_cap
            ),
            per_run_cap_usd=_env_float("AUTOPILOT_PER_RUN_USD", DEFAULT_PER_RUN_CAP_USD),
            default_model=os.environ.get("AUTOPILOT_MODEL", DEFAULT_MODEL),
            max_files=int(os.environ.get("AUTOPILOT_MAX_FILES", DEFAULT_MAX_FILES)),
            max_lines=int(os.environ.get("AUTOPILOT_MAX_LINES", DEFAULT_MAX_LINES)),
            repair_attempts=int(
                os.environ.get("AUTOPILOT_REPAIR_ATTEMPTS", DEFAULT_REPAIR_ATTEMPTS)
            ),
            automerge=_env_bool("AUTOPILOT_AUTOMERGE", default=False),
            dry_run=bool(args.dry_run),
            ci_run_url=ci_run_url,
        )


def _env_float(name: str, default: float, *, override: float | None = None) -> float:
    if override is not None:
        return float(override)
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def _env_bool(name: str, *, default: bool) -> bool:
    return os.environ.get(name, "true" if default else "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def autopilot_enabled() -> bool:
    return os.environ.get("AUTOPILOT_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# ======================================================================
# Budget gate (talks to the cost ledger) — fail-closed.
# ======================================================================


def spent_today_usd() -> float:
    """Today's autopilot model-cost from the shared ledger.

    Returns a sentinel ABOVE any sane cap when the ledger can't be reached, so
    the budget gate fails closed (no spend) rather than open.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
        from app.db.database import create_database_client
        from app.services.ai import cost_tracking as cts
    except Exception as exc:  # pragma: no cover - import guard
        print(f"[autopilot] cost ledger import failed, failing closed: {exc}", file=sys.stderr)
        return float("inf")
    try:
        db = create_database_client()
        spend = cts.get_daily_spend(db=db, agent_kind=AGENT_KIND)
        return float(spend.get("total_model_cost_usd") or 0.0)
    except Exception as exc:
        print(f"[autopilot] daily-spend query failed, failing closed: {exc}", file=sys.stderr)
        return float("inf")


def record_spend(*, model: str, input_tokens: int, output_tokens: int, note: str) -> float:
    """Persist this run's spend so the next run's budget gate sees it.

    Cost is priced from token counts via cost_tracking_service's OpenAI
    pricing table. Returns the recorded model cost (USD), 0.0 on failure.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app.db.database import create_database_client
        from app.services.ai import cost_tracking as cts
    except Exception as exc:  # pragma: no cover
        print(f"[autopilot] cannot record spend (import): {exc}", file=sys.stderr)
        return 0.0
    try:
        db = create_database_client()
        event = cts.log_cost_event(
            db=db,
            user_id=SYSTEM_USER_ID,
            agent_kind=AGENT_KIND,
            model=model or DEFAULT_MODEL,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            note=note[:500],
        )
        return float(event.get("model_cost_usd") or 0.0)
    except Exception as exc:
        print(f"[autopilot] cannot record spend (db): {exc}", file=sys.stderr)
        return 0.0


# ======================================================================
# GitHub I/O
# ======================================================================


def _gh_client() -> httpx.Client:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is required")
    return httpx.Client(
        timeout=30.0,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def fetch_issue(client: httpx.Client, *, repo: str, number: int) -> Issue:
    resp = client.get(f"https://api.github.com/repos/{repo}/issues/{number}")
    resp.raise_for_status()
    return Issue.from_api(resp.json())


def list_open_issues(client: httpx.Client, *, repo: str, limit: int = 100) -> list[Issue]:
    resp = client.get(
        f"https://api.github.com/repos/{repo}/issues",
        params={
            "state": "open",
            "per_page": min(limit, 100),
            "sort": "created",
            "direction": "asc",
        },
    )
    resp.raise_for_status()
    return [Issue.from_api(d) for d in resp.json()]


def busy_issue_numbers(client: httpx.Client, *, repo: str) -> set[int]:
    """Issue numbers that already have an open autopilot/issue-<n>-* PR."""
    resp = client.get(
        f"https://api.github.com/repos/{repo}/pulls",
        params={"state": "open", "per_page": 100},
    )
    resp.raise_for_status()
    busy: set[int] = set()
    for pr in resp.json():
        ref = str((pr.get("head") or {}).get("ref") or "")
        m = re.match(r"autopilot/issue-(\d+)-", ref)
        if m:
            busy.add(int(m.group(1)))
    return busy


def post_issue_comment(client: httpx.Client, *, repo: str, number: int, body: str) -> str | None:
    resp = client.post(
        f"https://api.github.com/repos/{repo}/issues/{number}/comments",
        json={"body": body},
    )
    if resp.status_code >= 300:
        print(
            f"[autopilot] comment failed: HTTP {resp.status_code} {resp.text[:200]}",
            file=sys.stderr,
        )
        return None
    return str(resp.json().get("html_url") or "")


# ======================================================================
# Shell helpers (git / gh / codex)
# ======================================================================


def run(
    cmd: list[str], *, cwd: Path | None = None, check: bool = True, timeout: int | None = None
) -> subprocess.CompletedProcess:
    print(f"[autopilot] $ {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=check,
        timeout=timeout,
        capture_output=True,
        text=True,
    )


def changed_paths_and_stats(worktree: Path) -> tuple[list[str], int, int]:
    """Staged+unstaged changes in the worktree relative to HEAD."""
    run(["git", "add", "-A"], cwd=worktree)
    names = run(["git", "diff", "--cached", "--name-only"], cwd=worktree).stdout.split("\n")
    paths = [p.strip() for p in names if p.strip()]
    numstat = run(["git", "diff", "--cached", "--numstat"], cwd=worktree).stdout
    insertions = deletions = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            insertions += int(parts[0]) if parts[0].isdigit() else 0
            deletions += int(parts[1]) if parts[1].isdigit() else 0
    return paths, insertions, deletions


def run_repo_checks(worktree: Path, *, changed_paths: list[str]) -> tuple[bool, str]:
    """Run the same gates scripts/check.py runs, scoped to what changed."""
    touched_backend = any(p.startswith(("backend/", "mcp_server/")) for p in changed_paths)
    touched_frontend = any(p.startswith("frontend/") for p in changed_paths)
    logs: list[str] = []

    def _step(name: str, cmd: list[str], cwd: Path) -> bool:
        proc = run(cmd, cwd=cwd, check=False, timeout=900)
        ok = proc.returncode == 0
        tail = (proc.stdout + proc.stderr)[-1500:]
        logs.append(f"### {name}: {'PASS' if ok else 'FAIL'}\n```\n{tail}\n```")
        return ok

    ok = True
    if touched_backend:
        ok &= _step("ruff", ["ruff", "check", "backend/app", "mcp_server/src"], worktree)
        ok &= _step("pytest", ["python", "-m", "pytest", "tests", "-q"], worktree / "backend")
    if touched_frontend:
        ok &= _step("jest", ["npm", "test", "--", "--watchAll=false"], worktree / "frontend")
    if not touched_backend and not touched_frontend:
        # docs-only / config change: a lint pass is enough signal.
        ok &= _step("ruff", ["ruff", "check", "backend/app"], worktree)
    return ok, "\n\n".join(logs)


def invoke_codex(*, prompt: str, model: str, worktree: Path) -> dict[str, Any]:
    """Run the OpenAI Codex CLI headless inside the worktree and parse it.

    ``codex exec`` is Codex's non-interactive mode. We run it fully automated
    (the worktree is an ephemeral CI sandbox) and ask for JSONL events so we
    can recover the result text and token usage. If usage isn't reported we
    estimate from the prompt + output length, so the cost ledger — and thus the
    daily budget gate — never sees a free run.

    NOTE: Codex CLI flags vary across versions. These are the documented
    full-automation flags; if your installed Codex differs, adjust here.
    """
    cmd = [
        "codex",
        "exec",
        "--json",
        "--model",
        model,
        "--dangerously-bypass-approvals-and-sandbox",
        prompt,
    ]
    proc = run(cmd, cwd=worktree, check=False, timeout=ENGINE_TIMEOUT_SECONDS)
    parsed = parse_codex_result(proc.stdout)
    if proc.returncode != 0 and not parsed.get("raw"):
        raise RuntimeError(f"codex exited {proc.returncode}: {(proc.stderr or proc.stdout)[:400]}")
    # Fallback so the budget gate always sees real spend.
    if parsed["input_tokens"] == 0:
        parsed["input_tokens"] = estimate_tokens(prompt)
    if parsed["output_tokens"] == 0:
        parsed["output_tokens"] = estimate_tokens(parsed["result_text"])
    parsed["model"] = parsed.get("model") or model
    return parsed


# ======================================================================
# Orchestration
# ======================================================================


def open_pull_request(
    *, worktree: Path, branch: str, base_branch: str, issue: Issue, summary: str, automerge: bool
) -> str | None:
    run(["git", "commit", "-m", _commit_message(issue, summary)], cwd=worktree)
    run(["git", "push", "--force-with-lease", "origin", f"HEAD:{branch}"], cwd=worktree)
    body = (
        f"Autonomous change by **Manifest Autopilot** resolving #{issue.number}.\n\n"
        f"{summary[:3000]}\n\n---\nCloses #{issue.number}\n\n"
        f"_Base branch `{base_branch}` — never `main`. A human promotes "
        f"`{base_branch}`→`main`. See docs/AUTOPILOT.md._"
    )
    create = run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            base_branch,
            "--head",
            branch,
            "--title",
            _commit_message(issue, summary).splitlines()[0],
            "--body",
            body,
            "--label",
            "autopilot",
        ],
        cwd=worktree,
        check=False,
    )
    url = (create.stdout or "").strip().splitlines()[-1] if create.stdout.strip() else None
    if create.returncode != 0:
        print(f"[autopilot] gh pr create failed: {create.stderr[:300]}", file=sys.stderr)
        return None
    if automerge and url:
        run(["gh", "pr", "merge", url, "--auto", "--squash"], cwd=worktree, check=False)
    return url


def _commit_message(issue: Issue, summary: str) -> str:
    kind = "fix" if ("bug" in issue.labels or "automated-test" in issue.labels) else "feat"
    subject = f"{kind}: {issue.title}".strip()
    return f"{subject[:72]}\n\n{summary[:500]}\n\nCloses #{issue.number}"


def append_journal(entry: dict[str, Any], *, repo_root: Path) -> None:
    journal = repo_root / "docs" / "autopilot" / "JOURNAL.md"
    try:
        line = (
            f"- `{entry.get('ts','')}` #{entry.get('issue')} — **{entry.get('action')}** "
            f"· model `{entry.get('model')}` · ${entry.get('cost_usd', 0):.4f}"
            + (f" · {entry.get('pr_url')}" if entry.get("pr_url") else "")
            + (f" · {entry.get('reason')}" if entry.get("reason") else "")
            + "\n"
        )
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:  # pragma: no cover
        print(f"[autopilot] journal append failed: {exc}", file=sys.stderr)


def comment_outcome(client, *, cfg: Config, issue: Issue, action: str, detail: str) -> None:
    if cfg.dry_run:
        print(f"[autopilot] (dry-run) would comment on #{issue.number}: {action} — {detail}")
        return
    body = (
        f"🤖 **Manifest Autopilot** — `{action}`\n\n{detail}\n\n---\n"
        f"_Autonomous self-improvement loop. {('CI: ' + cfg.ci_run_url) if cfg.ci_run_url else ''}_"
    )
    post_issue_comment(client, repo=cfg.repo, number=issue.number, body=body)


def do_one_issue(
    *, cfg: Config, client: httpx.Client, issue: Issue, repo_root: Path
) -> dict[str, Any]:
    """Implement → guard → verify → PR for a single issue."""
    model = model_for_issue(issue, default_model=cfg.default_model)
    branch = f"autopilot/issue-{issue.number}-{slugify(issue.title)}"
    worktree = repo_root / ".autopilot-worktree"

    # Fresh worktree off the base branch so the bot never works on main.
    run(["git", "fetch", "origin", cfg.base_branch], cwd=repo_root, check=False)
    run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo_root, check=False)
    base_ref = f"origin/{cfg.base_branch}"
    has_base = (
        run(["git", "rev-parse", "--verify", base_ref], cwd=repo_root, check=False).returncode == 0
    )
    run(
        [
            "git",
            "worktree",
            "add",
            "--force",
            "-B",
            f"{cfg.base_branch}-work",
            str(worktree),
            base_ref if has_base else "HEAD",
        ],
        cwd=repo_root,
    )

    prompt = build_implementation_prompt(
        issue=issue,
        base_branch=cfg.base_branch,
        per_run_cap_usd=cfg.per_run_cap_usd,
        max_files=cfg.max_files,
        max_lines=cfg.max_lines,
    )
    engine = invoke_codex(prompt=prompt, model=model, worktree=worktree)
    used_model = engine.get("model") or model
    tokens = {"input_tokens": engine["input_tokens"], "output_tokens": engine["output_tokens"]}

    # Did the engine explicitly decline?
    decline = declined_from_result(engine["result_text"])
    if decline:
        cost = record_spend(model=used_model, **tokens, note=f"declined #{issue.number}")
        comment_outcome(client, cfg=cfg, issue=issue, action="declined", detail=decline)
        return {"action": "declined", "model": used_model, "cost_usd": cost, "reason": decline}

    # Guard the diff and run the full CI-equivalent gate. If checks are red,
    # feed the failure back to the engine to fix and re-check — up to
    # cfg.repair_attempts times — so the PR only ever opens green. This is what
    # makes auto-merge safe: CI errors are repaired BEFORE the PR exists.
    changed: list[str] = []
    checks_log = ""
    attempt = 0
    while True:
        changed, ins, dele = changed_paths_and_stats(worktree)
        diff_check = evaluate_diff(
            changed_paths=changed,
            insertions=ins,
            deletions=dele,
            max_files=cfg.max_files,
            max_lines=cfg.max_lines,
        )
        if not diff_check["ok"]:
            cost = record_spend(
                model=used_model, **tokens, note=f"guard {diff_check['reason']} #{issue.number}"
            )
            comment_outcome(
                client,
                cfg=cfg,
                issue=issue,
                action="guard_rejected",
                detail=f"`{diff_check['reason']}` — {', '.join(diff_check['detail']) or 'n/a'}",
            )
            return {
                "action": "guard_rejected",
                "model": used_model,
                "cost_usd": cost,
                "reason": diff_check["reason"],
            }

        checks_ok, checks_log = run_repo_checks(worktree, changed_paths=changed)
        if checks_ok:
            break
        if attempt >= cfg.repair_attempts:
            cost = record_spend(
                model=used_model,
                **tokens,
                note=f"checks failed after {attempt} repair(s) #{issue.number}",
            )
            comment_outcome(
                client,
                cfg=cfg,
                issue=issue,
                action="checks_failed",
                detail=f"Still red after {attempt} repair attempt(s):\n\n{checks_log[:4500]}",
            )
            return {
                "action": "checks_failed",
                "model": used_model,
                "cost_usd": cost,
                "reason": "red_ci",
            }
        attempt += 1
        print(f"[autopilot] checks red — repair attempt {attempt}/{cfg.repair_attempts}")
        repair = invoke_codex(
            prompt=build_repair_prompt(
                issue=issue,
                checks_log=checks_log,
                max_files=cfg.max_files,
                max_lines=cfg.max_lines,
            ),
            model=used_model,
            worktree=worktree,
        )
        tokens["input_tokens"] += repair["input_tokens"]
        tokens["output_tokens"] += repair["output_tokens"]
        decline = declined_from_result(repair["result_text"])
        if decline:
            cost = record_spend(
                model=used_model, **tokens, note=f"declined during repair #{issue.number}"
            )
            comment_outcome(client, cfg=cfg, issue=issue, action="declined", detail=decline)
            return {"action": "declined", "model": used_model, "cost_usd": cost, "reason": decline}

    pr_url = None
    if cfg.dry_run:
        print(f"[autopilot] (dry-run) would open PR for #{issue.number} on {branch}")
        print(f"[autopilot] changed: {changed}")
    else:
        pr_url = open_pull_request(
            worktree=worktree,
            branch=branch,
            base_branch=cfg.base_branch,
            issue=issue,
            summary=engine["result_text"] or "Autonomous change.",
            automerge=cfg.automerge,
        )

    cost = record_spend(
        model=used_model, **tokens, note=f"pr {pr_url or 'dry-run'} #{issue.number}"
    )
    return {"action": "pr_opened", "model": used_model, "cost_usd": cost, "pr_url": pr_url}


def main() -> int:
    parser = argparse.ArgumentParser(description="Manifest Autopilot (v2 self-improvement loop)")
    parser.add_argument("--issue-number", type=int, default=0, help="Force a specific issue")
    parser.add_argument("--repo", type=str, default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--daily-cap", type=float, default=None, help="Override AUTOPILOT_DAILY_USD"
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan + run checks but open no PR")
    args = parser.parse_args()

    cfg = Config.from_env(args)
    if not cfg.repo:
        sys.exit("--repo is required (or set GITHUB_REPOSITORY)")
    repo_root = args.repo_root.resolve()

    # 1) Kill switch.
    if not autopilot_enabled() and not args.dry_run:
        print("[autopilot] AUTOPILOT_ENABLED != true — no-op exit.")
        return 0

    # 2) Budget gate (fail-closed).
    spent = spent_today_usd()
    budget = evaluate_budget(
        spent_today_usd=spent,
        daily_cap_usd=cfg.daily_cap_usd,
        per_run_cap_usd=cfg.per_run_cap_usd,
    )
    print(
        f"[autopilot] budget: spent_today=${spent:.4f} cap=${cfg.daily_cap_usd:.2f} "
        f"allowed={budget['allowed']} reason={budget['reason']}"
    )
    if not budget["allowed"] and not args.dry_run:
        print(f"[autopilot] budget gate closed ({budget['reason']}) — no-op exit.")
        return 0

    # 3) Select work.
    with _gh_client() as gh:
        if args.issue_number:
            issue = fetch_issue(gh, repo=cfg.repo, number=args.issue_number)
        else:
            issues = list_open_issues(gh, repo=cfg.repo)
            busy = busy_issue_numbers(gh, repo=cfg.repo)
            issue = select_issue(issues, busy_issue_numbers=busy)
        if issue is None:
            print("[autopilot] no eligible issue — no-op exit.")
            return 0
        print(f"[autopilot] selected #{issue.number}: {issue.title}")

        # 4-6) Implement, guard, verify, PR, record.
        outcome = do_one_issue(cfg=cfg, client=gh, issue=issue, repo_root=repo_root)

    append_journal(
        {
            "ts": _now_iso(),
            "issue": issue.number,
            "action": outcome.get("action"),
            "model": outcome.get("model"),
            "cost_usd": outcome.get("cost_usd", 0.0),
            "pr_url": outcome.get("pr_url"),
            "reason": outcome.get("reason"),
        },
        repo_root=repo_root,
    )
    print(
        f"[autopilot] done #{issue.number} action={outcome.get('action')} "
        f"cost=${outcome.get('cost_usd', 0.0):.4f}"
    )
    return 0


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    sys.exit(main())
