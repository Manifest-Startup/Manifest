"""Continuous production-test results ingest.

Receives one test-result POST per individual smoke-test execution
(typically from Playwright via `.github/workflows/production-tests.yml`),
persists it to `production_test_runs`, and on failure opens a deduped
GitHub issue through the existing `GitHubIssueService`.

This is intentionally test-runner-agnostic: anything that can POST the
documented JSON body to `/api/internal/production-tests/results` ends
up tracked the same way. Playwright is the canonical runner, but a
curl-based smoke check or a Cypress run would slot in identically.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from app.services.github_issue_service import (
    GitHubIssueConfigurationError,
    GitHubIssueDraft,
    GitHubIssueService,
)
from app.utils.logger import logger

TABLE = "production_test_runs"

# Issue creation only happens on these statuses. 'flaky' is logged but
# does NOT page anyone — it's just a trend signal.
FAILING_STATUSES = {"fail", "error"}

# Anything in this set is considered a terminal test outcome.
VALID_STATUSES = {"pass", "fail", "flaky", "error", "skipped"}
VALID_SEVERITIES = {"low", "medium", "high"}

# Severity → GitHub label mapping.
SEVERITY_LABEL = {
    "high": "severity:high",
    "medium": "severity:medium",
    "low": "severity:low",
}

DEFAULT_LABELS = ("bug", "automated-test", "production")


@dataclass
class TestResultPayload:
    """Incoming JSON shape for a single test result.

    Field names match what the Playwright reporter posts; route layer
    is responsible for validating with a Pydantic model before calling
    `record_test_run` with this dataclass.
    """

    test_name: str
    status: str
    suite: str | None = None
    environment: str = "production"
    severity: str = "medium"
    error_message: str | None = None
    stack_trace: str | None = None
    screenshot_url: str | None = None
    video_url: str | None = None
    har_url: str | None = None
    console_errors: list[Any] | None = None
    network_errors: list[Any] | None = None
    suspected_files: list[str] | None = None
    git_sha: str | None = None
    git_ref: str | None = None
    ci_run_url: str | None = None
    runner: str | None = None
    duration_ms: int | None = None
    started_at: str | None = None
    completed_at: str | None = None
    metadata: dict[str, Any] | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_title_key(title: str) -> str:
    """Match GitHubIssueService's dedupe key formatter."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", (title or "").lower())
    return " ".join(cleaned.split())


def _build_issue_title(test_name: str, error_message: str | None) -> str:
    """Stable dedupe key. First 100 chars of error_message keeps the
    title human-readable while still differentiating distinct failures
    on the same test."""
    head = (error_message or "").strip().splitlines()[0] if error_message else ""
    head = head[:100].rstrip()
    if head:
        return f"[prod-test] {test_name} — {head}"
    return f"[prod-test] {test_name} failure"


def _append_issue_summary(lines: list[str], payload: TestResultPayload, *, run_id: str) -> None:
    lines.append(f"**Automated production-test failure.** (run_id `{run_id}`)")
    lines.append("")
    lines.append(f"- **Test:** `{payload.test_name}`")
    if payload.suite:
        lines.append(f"- **Suite:** `{payload.suite}`")
    lines.append(f"- **Environment:** `{payload.environment}`")
    lines.append(f"- **Severity:** `{payload.severity}`")
    if payload.runner:
        lines.append(f"- **Runner:** `{payload.runner}`")
    if payload.git_sha:
        lines.append(f"- **Commit:** `{payload.git_sha}`")
    if payload.git_ref:
        lines.append(f"- **Ref:** `{payload.git_ref}`")
    if payload.ci_run_url:
        lines.append(f"- **CI run:** {payload.ci_run_url}")
    if payload.duration_ms is not None:
        lines.append(f"- **Duration:** {payload.duration_ms} ms")
    lines.append("")


def _append_issue_diagnostics(lines: list[str], payload: TestResultPayload) -> None:
    if payload.error_message:
        lines.append("### Error")
        lines.append("```")
        lines.append(payload.error_message.strip()[:2000])
        lines.append("```")

    if payload.stack_trace:
        lines.append("### Stack trace")
        lines.append("```")
        lines.append(payload.stack_trace.strip()[:4000])
        lines.append("```")

    if payload.console_errors:
        lines.append("### Console errors")
        lines.append("```json")
        lines.append(json.dumps(payload.console_errors[:10], indent=2))
        lines.append("```")

    if payload.network_errors:
        lines.append("### Failed network requests")
        lines.append("```json")
        lines.append(json.dumps(payload.network_errors[:10], indent=2))
        lines.append("```")

    if payload.suspected_files:
        lines.append("### Suspected files")
        for path in payload.suspected_files[:10]:
            lines.append(f"- `{path}`")


def _append_issue_attachments(lines: list[str], payload: TestResultPayload) -> None:
    if payload.screenshot_url:
        lines.append("")
        lines.append(f"![screenshot]({payload.screenshot_url})")
    if payload.video_url:
        lines.append("")
        lines.append(f"📹 Video: {payload.video_url}")
    if payload.har_url:
        lines.append("")
        lines.append(f"🌐 HAR: {payload.har_url}")


def _build_issue_body(payload: TestResultPayload, *, run_id: str) -> str:
    lines: list[str] = []
    _append_issue_summary(lines, payload, run_id=run_id)
    _append_issue_diagnostics(lines, payload)
    _append_issue_attachments(lines, payload)
    lines.append("")
    lines.append("---")
    lines.append("_Filed automatically by Manifest production-test runner._")
    return "\n".join(lines)


def _labels_for_payload(payload: TestResultPayload) -> list[str]:
    labels: list[str] = list(DEFAULT_LABELS)
    severity_label = SEVERITY_LABEL.get(payload.severity)
    if severity_label:
        labels.append(severity_label)
    return labels


# ---------- public API ----------


def record_test_run(*, db, payload: TestResultPayload) -> dict[str, Any]:
    """Persist one test execution. Always succeeds (never raises on DB error
    in normal usage — this is the hot path called from CI).

    Returns the inserted row (with id) on success.
    """
    if payload.status not in VALID_STATUSES:
        raise ValueError(
            f"invalid status {payload.status!r}; expected one of {sorted(VALID_STATUSES)}"
        )
    if payload.severity not in VALID_SEVERITIES:
        raise ValueError(
            f"invalid severity {payload.severity!r}; expected one of {sorted(VALID_SEVERITIES)}"
        )
    if not payload.test_name or not payload.test_name.strip():
        raise ValueError("test_name is required")

    row_id = str(uuid.uuid4())
    now = _now_iso()
    insert: dict[str, Any] = {
        "id": row_id,
        "test_name": payload.test_name.strip(),
        "suite": payload.suite,
        "environment": payload.environment or "production",
        "status": payload.status,
        "severity": payload.severity,
        "error_message": payload.error_message,
        "stack_trace": payload.stack_trace,
        "screenshot_url": payload.screenshot_url,
        "video_url": payload.video_url,
        "har_url": payload.har_url,
        "console_errors": json.dumps(payload.console_errors or []),
        "network_errors": json.dumps(payload.network_errors or []),
        "suspected_files": json.dumps(payload.suspected_files or []),
        "git_sha": payload.git_sha,
        "git_ref": payload.git_ref,
        "ci_run_url": payload.ci_run_url,
        "runner": payload.runner,
        "duration_ms": payload.duration_ms,
        "started_at": payload.started_at or now,
        "completed_at": payload.completed_at or now,
        "metadata": json.dumps(payload.metadata or {}),
        "created_at": now,
    }
    response = db.table(TABLE).insert(insert).execute()
    row = response.data
    if isinstance(row, list):
        row = row[0] if row else None
    if not row:
        raise RuntimeError("Failed to persist production_test_run row")
    return dict(row)


def _set_issue_linkage(*, db, row_id: str, updates: dict[str, Any]) -> None:
    """Idempotent partial update of the test_run row with issue metadata."""
    try:
        db.table(TABLE).update(updates).eq("id", row_id).execute()
    except Exception as exc:
        logger.warning("[prod_test] failed to record issue linkage row=%s: %s", row_id, exc)


async def maybe_create_issue_for_failure(
    *,
    db,
    payload: TestResultPayload,
    persisted_row: dict[str, Any],
    repo: str | None = None,
    github_service: GitHubIssueService | None = None,
    httpx_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """For failing rows, open (or skip, on dedupe) a GitHub issue.

    Returns a dict describing what happened — never raises on GitHub
    misconfiguration; the test row stays persisted and the dispatch
    result is logged for ops to investigate.
    """
    if payload.status not in FAILING_STATUSES:
        return {"action": "skip_non_failure", "status": payload.status}

    repo = repo or os.getenv("MANIFEST_GITHUB_REPO")
    if not repo:
        logger.info(
            "[prod_test] failure recorded but MANIFEST_GITHUB_REPO not set; "
            "issue not opened (row=%s)",
            persisted_row.get("id"),
        )
        return {"action": "skip_no_repo"}

    title = _build_issue_title(payload.test_name, payload.error_message)
    body = _build_issue_body(payload, run_id=str(persisted_row.get("id") or ""))
    labels = _labels_for_payload(payload)
    draft = GitHubIssueDraft(title=title, body=body, labels=labels)

    svc = github_service or GitHubIssueService()
    owns_client = False
    if httpx_client is None:
        httpx_client = httpx.AsyncClient(timeout=30.0)
        owns_client = True

    try:
        result = await svc.create_issues(
            httpx_client,
            repo=repo,
            issue_drafts=[draft],
        )
    except GitHubIssueConfigurationError as exc:
        logger.warning("[prod_test] GitHub issue creation skipped (config): %s", exc)
        return {"action": "skip_no_token", "error": str(exc)}
    except Exception as exc:
        logger.error("[prod_test] GitHub issue creation failed: %s", exc)
        return {"action": "error", "error": str(exc)}
    finally:
        if owns_client:
            await httpx_client.aclose()

    created = result.get("created_issues") or []
    skipped = result.get("skipped_issues") or []
    row_id = str(persisted_row.get("id"))

    if created:
        issue = created[0]
        _set_issue_linkage(
            db=db,
            row_id=row_id,
            updates={
                "github_issue_number": issue.get("number"),
                "github_issue_url": issue.get("url"),
            },
        )
        return {"action": "created", "issue": issue}

    if skipped:
        existing_url = await _find_open_issue_url(
            client=httpx_client if not owns_client else None,
            repo=repo,
            title_key=_normalize_title_key(title),
        )
        if existing_url:
            _set_issue_linkage(
                db=db,
                row_id=row_id,
                updates={"linked_existing_issue_url": existing_url},
            )
        return {"action": "deduped", "existing_url": existing_url}

    return {"action": "noop"}


async def _find_open_issue_url(
    *, client: httpx.AsyncClient | None, repo: str, title_key: str
) -> str | None:
    """Best-effort lookup of the matching open issue URL for dashboard linking."""
    token = os.getenv("MANIFEST_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        return None
    owns = False
    if client is None:
        client = httpx.AsyncClient(timeout=15.0)
        owns = True
    try:
        response = await client.get(
            f"https://api.github.com/repos/{repo}/issues",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={"state": "open", "per_page": 100},
        )
        response.raise_for_status()
        for issue in response.json():
            if issue.get("pull_request"):
                continue
            if _normalize_title_key(issue.get("title", "")) == title_key:
                return issue.get("html_url")
    except Exception as exc:
        logger.debug("[prod_test] open-issue lookup failed: %s", exc)
        return None
    finally:
        if owns:
            await client.aclose()
    return None


# ---------- read APIs (for ops / future admin dashboard) ----------


def list_recent_runs(
    *,
    db,
    limit: int = 50,
    status: str | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 500))
    query = db.table(TABLE).select("*").order("started_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    response = query.execute()
    return [dict(r) for r in (response.data or [])]


def get_failure_stats(*, db, hours: int = 24) -> dict[str, Any]:
    """Aggregate stats for the trailing `hours` window."""
    since = datetime.now(timezone.utc).timestamp() - max(1, int(hours)) * 3600
    since_iso = datetime.fromtimestamp(since, tz=timezone.utc).isoformat()
    response = (
        db.table(TABLE)
        .select("*")
        .gte("started_at", since_iso)
        .order("started_at", desc=True)
        .limit(2000)
        .execute()
    )
    rows = list(response.data or [])
    counts = {"pass": 0, "fail": 0, "flaky": 0, "error": 0, "skipped": 0}
    by_test_fail: dict[str, int] = {}
    issues_opened = 0
    issues_deduped = 0
    for row in rows:
        status = str(row.get("status") or "")
        if status in counts:
            counts[status] += 1
        if status in FAILING_STATUSES:
            tn = str(row.get("test_name") or "unknown")
            by_test_fail[tn] = by_test_fail.get(tn, 0) + 1
            if row.get("github_issue_number"):
                issues_opened += 1
            elif row.get("linked_existing_issue_url"):
                issues_deduped += 1
    total = sum(counts.values())
    fail_count = counts["fail"] + counts["error"]
    return {
        "window_hours": hours,
        "total_runs": total,
        "counts_by_status": counts,
        "failure_rate": (fail_count / total) if total else 0.0,
        "top_failing_tests": sorted(
            ({"test_name": k, "failures": v} for k, v in by_test_fail.items()),
            key=lambda item: item["failures"],
            reverse=True,
        )[:10],
        "issues_opened": issues_opened,
        "issues_deduped": issues_deduped,
    }
