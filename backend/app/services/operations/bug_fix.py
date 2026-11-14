"""Bug-fix agent attempt ingest.

Receives one attempt record per autonomous bug-fix run (typically from
the GitHub Actions runner at `.github/workflows/bug-fix-agent.yml`
calling `backend/scripts/run_bugfix_agent.py`).

v1 = diagnose-only: agent reads a labeled GitHub issue, generates a
markdown diagnosis, posts it as a comment, and records the attempt
here. v2 will extend with draft-PR creation; the schema already has
the columns reserved.

This module is read/write but NEVER calls GitHub itself — the GHA
runner handles the GitHub API. We only persist what happened.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import logger

TABLE = "bug_fix_attempts"

VALID_ACTIONS = {
    "diagnosis_posted",
    "declined",
    "draft_pr_opened",  # reserved for v2
    "draft_pr_updated",  # reserved for v2
    "failed",
}

VALID_CONFIDENCE = {"low", "medium", "high"}


class BugFixError(Exception):
    """Raised on validation failure during attempt ingest."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_jsonb(value: Any) -> str:
    if value is None:
        return "[]" if isinstance(value, list) else "{}"
    return json.dumps(value)


def record_attempt(*, db, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a single bug-fix attempt. Raises BugFixError on bad input."""
    action = str(payload.get("action") or "").strip()
    if action not in VALID_ACTIONS:
        raise BugFixError(f"invalid action {action!r}; expected one of {sorted(VALID_ACTIONS)}")

    confidence = payload.get("confidence")
    if confidence is not None and confidence not in VALID_CONFIDENCE:
        raise BugFixError(
            f"invalid confidence {confidence!r}; expected one of {sorted(VALID_CONFIDENCE)}"
        )

    issue_number = payload.get("github_issue_number")
    if issue_number is None:
        raise BugFixError("github_issue_number is required")
    try:
        issue_number = int(issue_number)
    except (TypeError, ValueError) as exc:
        raise BugFixError("github_issue_number must be an integer") from exc

    insert = {
        "id": str(uuid.uuid4()),
        "github_issue_number": issue_number,
        "github_issue_url": payload.get("github_issue_url"),
        "issue_title": payload.get("issue_title"),
        "source_environment": payload.get("source_environment"),
        "source_test_run_id": payload.get("source_test_run_id"),
        "action": action,
        "confidence": confidence,
        "diagnosis_markdown": payload.get("diagnosis_markdown"),
        "risks": _coerce_jsonb(payload.get("risks") or []),
        "suspected_files": _coerce_jsonb(payload.get("suspected_files") or []),
        "branch_name": payload.get("branch_name"),
        "draft_pr_number": payload.get("draft_pr_number"),
        "draft_pr_url": payload.get("draft_pr_url"),
        "model": payload.get("model"),
        "input_tokens": max(0, int(payload.get("input_tokens") or 0)),
        "output_tokens": max(0, int(payload.get("output_tokens") or 0)),
        "model_cost_usd": max(0.0, float(payload.get("model_cost_usd") or 0)),
        "error_message": payload.get("error_message"),
        "runner": payload.get("runner"),
        "ci_run_url": payload.get("ci_run_url"),
        "metadata": _coerce_jsonb(payload.get("metadata") or {}),
        "created_at": _now_iso(),
    }
    response = db.table(TABLE).insert(insert).execute()
    row = response.data
    if isinstance(row, list):
        row = row[0] if row else None
    if not row:
        raise BugFixError("Failed to persist bug_fix_attempt row")

    logger.info(
        "[bug_fix] attempt issue=%s action=%s confidence=%s model=%s",
        issue_number,
        action,
        confidence,
        payload.get("model"),
    )
    return dict(row)


def list_recent_attempts(
    *,
    db,
    limit: int = 50,
    issue_number: int | None = None,
    action: str | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 500))
    query = db.table(TABLE).select("*").order("created_at", desc=True).limit(limit)
    if issue_number is not None:
        query = query.eq("github_issue_number", int(issue_number))
    if action:
        query = query.eq("action", action)
    response = query.execute()
    return [dict(r) for r in (response.data or [])]


def get_attempt_stats(*, db, hours: int = 168) -> dict[str, Any]:
    """Aggregate trailing-window stats for the admin dashboard."""
    since = datetime.now(timezone.utc).timestamp() - max(1, int(hours)) * 3600
    since_iso = datetime.fromtimestamp(since, tz=timezone.utc).isoformat()
    response = (
        db.table(TABLE)
        .select("*")
        .gte("created_at", since_iso)
        .order("created_at", desc=True)
        .limit(1000)
        .execute()
    )
    rows = list(response.data or [])
    by_action: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    by_issue: dict[int, int] = {}
    total_cost = 0.0
    for row in rows:
        a = str(row.get("action") or "unknown")
        by_action[a] = by_action.get(a, 0) + 1
        c = row.get("confidence")
        if c:
            by_confidence[str(c)] = by_confidence.get(str(c), 0) + 1
        n = row.get("github_issue_number")
        if n is not None:
            try:
                key = int(n)
            except (TypeError, ValueError):
                continue
            by_issue[key] = by_issue.get(key, 0) + 1
        total_cost += float(row.get("model_cost_usd") or 0)
    return {
        "window_hours": hours,
        "total_attempts": len(rows),
        "by_action": by_action,
        "by_confidence": by_confidence,
        "issues_touched": len(by_issue),
        "total_model_cost_usd": round(total_cost, 6),
        "top_retried_issues": sorted(
            ({"github_issue_number": k, "attempts": v} for k, v in by_issue.items()),
            key=lambda item: item["attempts"],
            reverse=True,
        )[:10],
    }
