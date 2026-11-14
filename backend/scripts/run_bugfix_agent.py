"""Bug-fix agent runner — diagnose-only (v1).

Invoked by .github/workflows/bug-fix-agent.yml on issues.labeled with
the `automated-test` label. For each fired event:

  1. Pull the labeled issue from the GitHub REST API.
  2. Parse the structured body emitted by the Manifest production-test
     reporter (suspected_files block, error message, stack trace).
  3. Read up to N suspected files from the local checkout.
  4. Ask OpenAI to produce a STRUCTURED JSON diagnosis.
  5. Post the diagnosis as an issue comment.
  6. POST the attempt record to the deployed backend's internal
     /api/internal/bug-fix/attempts.

The runner is intentionally stand-alone (no FastAPI imports). The
backend stays the source of truth for persistence; this script is just
a CI worker that talks to GitHub + OpenAI + the backend's internal
ingest endpoint.

Required env (provided by the GHA workflow):
  GITHUB_TOKEN              — GitHub API token (workflow-provided)
  GITHUB_REPOSITORY         — owner/repo (workflow-provided)
  GITHUB_RUN_ID             — for the ci_run_url link (workflow-provided)
  OPENAI_API_KEY            — for the LLM call
  MANIFEST_INTERNAL_API_URL — base URL of the deployed backend
  MANIFEST_AGENT_LOOP_SECRET — backend X-Manifest-Agent-Key
  BUGFIX_AGENT_ISSUE_NUMBER — issue to diagnose (set by the workflow)

Usage:
  python backend/scripts/run_bugfix_agent.py --issue-number 123
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx


MAX_FILE_BYTES = 12_000
MAX_SUSPECTED_FILES = 4
LLM_MODEL = os.environ.get("BUGFIX_AGENT_MODEL", "gpt-4o-mini")
LLM_TIMEOUT_SECONDS = 60

PRICING_USD_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4-turbo": (10.00, 30.00),
}
DEFAULT_PRICING = (1.00, 3.00)

SYSTEM_PROMPT = (
    "You are Manifest's diagnose-only bug-fix agent. You are looking at "
    "a GitHub issue that was auto-filed because a production smoke test "
    "failed. Your output is a STRUCTURED JSON diagnosis only — do NOT "
    "produce a code patch. The goal is to help a human engineer locate "
    "the bug, not to fix it autonomously.\n\n"
    "Rules:\n"
    "- Be conservative. If the issue body lacks enough signal (no "
    "  stack trace, no suspected files), set decline_reason and stop.\n"
    "- Cite the exact file + line in suspected_locations when the "
    "  stack trace gives them.\n"
    "- candidate_fix should be 3-6 lines describing the change "
    "  direction, not a finished patch.\n"
    "- Set confidence='low' for guesses, 'high' only when you can name "
    "  the exact failing line and a likely root cause.\n"
    "- Return STRICT JSON. No prose outside the object. No code fences."
)

OUTPUT_SCHEMA_HINT = json.dumps(
    {
        "decline_reason": "string|null",
        "root_cause": "string",
        "suspected_locations": [
            {"path": "string", "line_hint": "integer|null", "why": "string"}
        ],
        "candidate_fix": "string",
        "risks": ["string"],
        "confidence": "low|medium|high",
    },
    indent=2,
)


@dataclass
class GitHubIssue:
    number: int
    title: str
    url: str
    body: str
    labels: list[str] = field(default_factory=list)


@dataclass
class ParsedIssue:
    suspected_files: list[str]
    error_message: str | None
    stack_trace: str | None
    test_name: str | None
    environment: str | None


# ---------- GitHub fetch + post ----------


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


def fetch_issue(client: httpx.Client, *, repo: str, number: int) -> GitHubIssue:
    response = client.get(f"https://api.github.com/repos/{repo}/issues/{number}")
    response.raise_for_status()
    data = response.json()
    return GitHubIssue(
        number=int(data.get("number") or number),
        title=str(data.get("title") or ""),
        url=str(data.get("html_url") or ""),
        body=str(data.get("body") or ""),
        labels=[str(label.get("name") or "") for label in (data.get("labels") or [])],
    )


def post_issue_comment(
    client: httpx.Client, *, repo: str, number: int, body: str
) -> str | None:
    response = client.post(
        f"https://api.github.com/repos/{repo}/issues/{number}/comments",
        json={"body": body},
    )
    if response.status_code >= 300:
        print(
            f"[bugfix-agent] failed to post comment: HTTP {response.status_code} "
            f"{response.text[:200]}",
            file=sys.stderr,
        )
        return None
    data = response.json()
    return str(data.get("html_url") or "")


# ---------- issue body parsing ----------


def parse_issue_body(body: str) -> ParsedIssue:
    """Best-effort extraction. The production-test reporter writes a
    deterministic markdown layout; everything here is defensive against
    older issue styles too."""
    suspected_files = _extract_suspected_files(body)
    error_message = _extract_section(body, "### Error")
    stack_trace = _extract_section(body, "### Stack trace")
    test_name = _extract_test_name(body)
    environment = _extract_inline(body, "Environment")
    return ParsedIssue(
        suspected_files=suspected_files,
        error_message=error_message,
        stack_trace=stack_trace,
        test_name=test_name,
        environment=environment,
    )


def _extract_section(body: str, heading: str) -> str | None:
    if heading not in body:
        return None
    after = body.split(heading, 1)[1]
    end_markers = ["\n### ", "\n---"]
    cut = len(after)
    for m in end_markers:
        idx = after.find(m)
        if idx != -1:
            cut = min(cut, idx)
    chunk = after[:cut].strip()
    if chunk.startswith("```"):
        chunk = chunk.strip("`").lstrip("\n").rstrip("\n")
    return chunk or None


def _extract_suspected_files(body: str) -> list[str]:
    section = _extract_section(body, "### Suspected files")
    if not section:
        return []
    out: list[str] = []
    for line in section.splitlines():
        stripped = line.strip().lstrip("-").strip().strip("`")
        if not stripped:
            continue
        if "/" not in stripped and "." not in stripped:
            continue
        if stripped.startswith("/") or stripped.startswith(".."):
            continue
        out.append(stripped)
        if len(out) >= MAX_SUSPECTED_FILES:
            break
    return out


def _extract_test_name(body: str) -> str | None:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("- **Test:**"):
            rest = line.split("**", 2)[-1].strip().strip("`")
            return rest or None
    return None


def _extract_inline(body: str, label: str) -> str | None:
    needle = f"**{label}:**"
    for line in body.splitlines():
        if needle in line:
            return line.split(needle, 1)[1].strip().strip("`") or None
    return None


# ---------- LLM call ----------


def read_repo_files(paths: list[str], repo_root: Path) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for path in paths:
        try:
            full = (repo_root / path).resolve()
        except Exception:
            continue
        try:
            full.relative_to(repo_root.resolve())
        except ValueError:
            continue
        if not full.exists() or not full.is_file():
            out.append({"path": path, "content": "[file not found in checkout]"})
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            out.append({"path": path, "content": f"[unreadable: {exc}]"})
            continue
        if len(text) > MAX_FILE_BYTES:
            text = text[:MAX_FILE_BYTES] + f"\n\n... [truncated at {MAX_FILE_BYTES} bytes] ..."
        out.append({"path": path, "content": text})
    return out


def call_llm(
    *, issue: GitHubIssue, parsed: ParsedIssue, files: list[dict[str, str]]
) -> tuple[dict[str, Any], dict[str, int], str]:
    """Returns (parsed_json, usage_dict, model_used)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("openai SDK not installed in the runner env") from exc

    user_content = _render_llm_user_block(issue=issue, parsed=parsed, files=files)
    client = OpenAI(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
        max_tokens=1500,
    )
    content = response.choices[0].message.content or ""
    try:
        parsed_json = json.loads(content)
    except json.JSONDecodeError:
        cleaned = content.strip().lstrip("`").rstrip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        parsed_json = json.loads(cleaned)
    usage = response.usage
    usage_dict = {
        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
    }
    return parsed_json, usage_dict, LLM_MODEL


def _render_llm_user_block(
    *, issue: GitHubIssue, parsed: ParsedIssue, files: list[dict[str, str]]
) -> str:
    parts: list[str] = []
    parts.append(f"GITHUB ISSUE #{issue.number}: {issue.title}")
    parts.append(f"URL: {issue.url}")
    parts.append(f"LABELS: {', '.join(issue.labels) or '(none)'}")
    parts.append("")
    if parsed.test_name:
        parts.append(f"FAILING TEST: {parsed.test_name}")
    if parsed.environment:
        parts.append(f"ENVIRONMENT: {parsed.environment}")
    parts.append("")
    if parsed.error_message:
        parts.append("ERROR MESSAGE:")
        parts.append("```")
        parts.append(parsed.error_message[:1500])
        parts.append("```")
        parts.append("")
    if parsed.stack_trace:
        parts.append("STACK TRACE:")
        parts.append("```")
        parts.append(parsed.stack_trace[:3000])
        parts.append("```")
        parts.append("")
    if files:
        parts.append("SUSPECTED FILE CONTENTS:")
        for f in files:
            parts.append(f"--- FILE: {f['path']} ---")
            parts.append(f["content"])
            parts.append("")
    parts.append("Return STRICT JSON matching this schema:")
    parts.append(OUTPUT_SCHEMA_HINT)
    return "\n".join(parts)


# ---------- comment rendering ----------


def render_diagnosis_comment(
    *, diagnosis: dict[str, Any], model: str
) -> str:
    lines: list[str] = []
    lines.append("🤖 **Automated diagnosis — Manifest bug-fix agent (v1, diagnose-only)**")
    lines.append("")
    confidence = str(diagnosis.get("confidence") or "low")
    lines.append(f"_Confidence: **{confidence}** · Model: `{model}` · Action: comment-only (no patch)._")
    lines.append("")
    root = (diagnosis.get("root_cause") or "").strip()
    if root:
        lines.append("### Likely root cause")
        lines.append(root)
        lines.append("")
    locations = diagnosis.get("suspected_locations") or []
    if locations:
        lines.append("### Where to look")
        for loc in locations[:6]:
            path = str(loc.get("path") or "?")
            line_hint = loc.get("line_hint")
            why = (loc.get("why") or "").strip()
            tag = f"`{path}`" + (f":{line_hint}" if line_hint else "")
            lines.append(f"- {tag} — {why}" if why else f"- {tag}")
        lines.append("")
    candidate = (diagnosis.get("candidate_fix") or "").strip()
    if candidate:
        lines.append("### Candidate fix direction")
        lines.append(candidate)
        lines.append("")
    risks = diagnosis.get("risks") or []
    if risks:
        lines.append("### Risks / caveats")
        for r in risks[:6]:
            lines.append(f"- {r}")
        lines.append("")
    lines.append("---")
    lines.append("_This is a v1 diagnose-only agent. It will not open a PR. Please review the diagnosis and apply a fix manually if it's correct._")
    return "\n".join(lines)


def render_decline_comment(*, reason: str, model: str) -> str:
    return (
        "🤖 **Manifest bug-fix agent — declined to diagnose**\n\n"
        f"_Model: `{model}` · Reason:_ {reason.strip()}\n\n"
        "---\n"
        "_The agent didn't see enough signal (e.g. no stack trace, no suspected files, "
        "or a state it explicitly couldn't reason about). A human triage pass would help here._"
    )


# ---------- attempt persistence ----------


def _model_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = PRICING_USD_PER_1M.get(model, DEFAULT_PRICING)
    return round(
        (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000.0, 6
    )


def post_attempt(
    *,
    payload: dict[str, Any],
) -> None:
    base = (os.environ.get("MANIFEST_INTERNAL_API_URL") or "").rstrip("/")
    secret = os.environ.get("MANIFEST_AGENT_LOOP_SECRET")
    if not base or not secret:
        print(
            "[bugfix-agent] MANIFEST_INTERNAL_API_URL / MANIFEST_AGENT_LOOP_SECRET "
            "missing — skipping backend persistence.",
            file=sys.stderr,
        )
        return
    try:
        response = httpx.post(
            f"{base}/api/internal/bug-fix/attempts",
            json=payload,
            headers={"X-Manifest-Agent-Key": secret},
            timeout=30.0,
        )
        if response.status_code >= 300:
            print(
                f"[bugfix-agent] attempt POST failed: HTTP {response.status_code} "
                f"{response.text[:200]}",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"[bugfix-agent] attempt POST error: {exc}", file=sys.stderr)


# ---------- main ----------


def main() -> int:
    parser = argparse.ArgumentParser(description="Manifest bug-fix agent (v1)")
    parser.add_argument(
        "--issue-number",
        type=int,
        default=int(os.environ.get("BUGFIX_AGENT_ISSUE_NUMBER") or 0),
        help="GitHub issue number to diagnose",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="GitHub repo (owner/name)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Local repo checkout root",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip the issue comment + backend POST; print what would be sent",
    )
    args = parser.parse_args()

    if not args.issue_number:
        sys.exit("--issue-number is required (or set BUGFIX_AGENT_ISSUE_NUMBER)")
    if not args.repo:
        sys.exit("--repo is required (or set GITHUB_REPOSITORY)")

    ci_run_url = None
    if os.environ.get("GITHUB_SERVER_URL") and os.environ.get("GITHUB_RUN_ID"):
        ci_run_url = (
            f"{os.environ['GITHUB_SERVER_URL']}/{args.repo}/"
            f"actions/runs/{os.environ['GITHUB_RUN_ID']}"
        )

    with _gh_client() as gh:
        issue = fetch_issue(gh, repo=args.repo, number=args.issue_number)
        parsed = parse_issue_body(issue.body)
        files = read_repo_files(parsed.suspected_files, args.repo_root)

        action = "diagnosis_posted"
        diagnosis: dict[str, Any] = {}
        usage = {"input_tokens": 0, "output_tokens": 0}
        model_used = LLM_MODEL
        error_message: str | None = None
        comment_body: str

        try:
            diagnosis, usage, model_used = call_llm(
                issue=issue, parsed=parsed, files=files,
            )
        except Exception as exc:
            action = "failed"
            error_message = str(exc)
            comment_body = render_decline_comment(
                reason=f"agent crashed: {exc}", model=model_used,
            )
        else:
            decline_reason = (diagnosis.get("decline_reason") or "").strip()
            if decline_reason:
                action = "declined"
                comment_body = render_decline_comment(
                    reason=decline_reason, model=model_used,
                )
            else:
                comment_body = render_diagnosis_comment(
                    diagnosis=diagnosis, model=model_used,
                )

        if args.dry_run:
            print("=== would post comment ===")
            print(comment_body)
            comment_url = None
        else:
            comment_url = post_issue_comment(
                gh, repo=args.repo, number=args.issue_number, body=comment_body,
            )

    model_cost = _model_cost_usd(
        model_used, usage["input_tokens"], usage["output_tokens"]
    )

    attempt_payload = {
        "github_issue_number": issue.number,
        "github_issue_url": issue.url,
        "issue_title": issue.title,
        "source_environment": parsed.environment,
        "action": action,
        "confidence": diagnosis.get("confidence") if action == "diagnosis_posted" else None,
        "diagnosis_markdown": comment_body,
        "risks": diagnosis.get("risks") or [],
        "suspected_files": parsed.suspected_files,
        "model": model_used,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "model_cost_usd": model_cost,
        "error_message": error_message,
        "runner": "github-actions:bug-fix-agent",
        "ci_run_url": ci_run_url,
        "metadata": {"comment_url": comment_url, "test_name": parsed.test_name},
    }

    if args.dry_run:
        print("\n=== would POST attempt ===")
        print(json.dumps(attempt_payload, indent=2))
    else:
        post_attempt(payload=attempt_payload)

    print(
        f"[bugfix-agent] done issue=#{issue.number} action={action} "
        f"model_cost=${model_cost:.6f}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
