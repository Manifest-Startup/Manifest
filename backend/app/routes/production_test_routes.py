"""Internal production-test ingest + ops read endpoints.

Playwright (and any other smoke runner) POSTs results here from CI.
Authenticated with the same ``X-Manifest-Agent-Key`` header as other
internal agent-loop routes.

See docs/PRODUCTION_TESTING.md.
"""

from __future__ import annotations

from typing import Any

from app.db.database import create_database_client
from app.routes.dependencies import require_agent_loop_key
from app.services.operations import production_tests as pts
from app.utils.logger import logger
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/api/internal/production-tests",
    tags=["Internal Agent Loop"],
    include_in_schema=False,
)


class TestResultBody(BaseModel):
    test_name: str = Field(..., min_length=1, max_length=300)
    status: str = Field(..., description="pass | fail | flaky | error | skipped")
    suite: str | None = Field(default=None, max_length=300)
    environment: str = Field(default="production", max_length=120)
    severity: str = Field(default="medium", description="low | medium | high")

    error_message: str | None = Field(default=None, max_length=10_000)
    stack_trace: str | None = Field(default=None, max_length=20_000)

    screenshot_url: str | None = Field(default=None, max_length=1000)
    video_url: str | None = Field(default=None, max_length=1000)
    har_url: str | None = Field(default=None, max_length=1000)
    console_errors: list[Any] | None = None
    network_errors: list[Any] | None = None
    suspected_files: list[str] | None = None

    git_sha: str | None = Field(default=None, max_length=120)
    git_ref: str | None = Field(default=None, max_length=400)
    ci_run_url: str | None = Field(default=None, max_length=1000)
    runner: str | None = Field(default=None, max_length=120)
    duration_ms: int | None = None

    started_at: str | None = None
    completed_at: str | None = None

    create_github_issue: bool = Field(
        default=True,
        description="When true (default) and the status is failing, file or dedupe a GitHub issue.",
    )
    metadata: dict[str, Any] | None = None


@router.post("/results")
async def post_test_result(
    body: TestResultBody,
    _agent: str = Depends(require_agent_loop_key),
):
    """Ingest one test execution. On failing statuses, also files/dedupes a GitHub issue."""
    payload = pts.TestResultPayload(
        test_name=body.test_name,
        status=body.status,
        suite=body.suite,
        environment=body.environment,
        severity=body.severity,
        error_message=body.error_message,
        stack_trace=body.stack_trace,
        screenshot_url=body.screenshot_url,
        video_url=body.video_url,
        har_url=body.har_url,
        console_errors=body.console_errors,
        network_errors=body.network_errors,
        suspected_files=body.suspected_files,
        git_sha=body.git_sha,
        git_ref=body.git_ref,
        ci_run_url=body.ci_run_url,
        runner=body.runner,
        duration_ms=body.duration_ms,
        started_at=body.started_at,
        completed_at=body.completed_at,
        metadata=body.metadata,
    )
    db = create_database_client()
    try:
        row = pts.record_test_run(db=db, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("[ProdTestRoutes] persistence failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to record test run.") from None

    dispatch: dict[str, Any] = {"action": "skipped_by_request"}
    if body.create_github_issue:
        try:
            dispatch = await pts.maybe_create_issue_for_failure(
                db=db, payload=payload, persisted_row=row
            )
        except Exception as exc:
            logger.warning("[ProdTestRoutes] issue dispatch error: %s", exc)
            dispatch = {"action": "error", "error": str(exc)}

    return {
        "run_id": row.get("id"),
        "status": row.get("status"),
        "github": dispatch,
    }


@router.get("/recent")
async def get_recent_runs(
    limit: int = 50,
    status: str | None = None,
    _agent: str = Depends(require_agent_loop_key),
):
    db = create_database_client()
    return {
        "runs": pts.list_recent_runs(db=db, limit=limit, status=status),
    }


@router.get("/stats")
async def get_stats(
    hours: int = 24,
    _agent: str = Depends(require_agent_loop_key),
):
    db = create_database_client()
    return pts.get_failure_stats(db=db, hours=hours)
