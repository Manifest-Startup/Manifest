"""Internal bug-fix-agent attempt ingest + ops read endpoints.

The GHA bug-fix-agent runner POSTs one attempt record per fired
workflow. Authenticated with the same ``X-Manifest-Agent-Key`` header
as the other internal agent-loop routes.

See docs/BUG_FIX_AGENT.md.
"""

from __future__ import annotations

from typing import Any

from app.db.database import create_database_client
from app.routes.dependencies import require_agent_loop_key
from app.services.operations import bug_fix as bfs
from app.utils.logger import logger
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/api/internal/bug-fix",
    tags=["Internal Agent Loop"],
    include_in_schema=False,
)


class BugFixAttemptBody(BaseModel):
    github_issue_number: int
    github_issue_url: str | None = Field(default=None, max_length=1000)
    issue_title: str | None = Field(default=None, max_length=500)
    source_environment: str | None = Field(default=None, max_length=120)
    source_test_run_id: str | None = None

    action: str = Field(..., description="diagnosis_posted | declined | failed (v1)")
    confidence: str | None = Field(default=None, description="low | medium | high")

    diagnosis_markdown: str | None = Field(default=None, max_length=20_000)
    risks: list[Any] | None = None
    suspected_files: list[str] | None = None

    branch_name: str | None = Field(default=None, max_length=400)
    draft_pr_number: int | None = None
    draft_pr_url: str | None = Field(default=None, max_length=1000)

    model: str | None = Field(default=None, max_length=120)
    input_tokens: int = 0
    output_tokens: int = 0
    model_cost_usd: float = 0.0

    error_message: str | None = Field(default=None, max_length=5_000)
    runner: str | None = Field(default=None, max_length=200)
    ci_run_url: str | None = Field(default=None, max_length=1000)

    metadata: dict[str, Any] | None = None


@router.post("/attempts")
async def post_attempt(
    body: BugFixAttemptBody,
    _agent: str = Depends(require_agent_loop_key),
):
    db = create_database_client()
    try:
        row = bfs.record_attempt(db=db, payload=body.model_dump())
    except bfs.BugFixError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover — defensive
        logger.error("[BugFixRoutes] persistence failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to record bug-fix attempt.") from None
    return {"attempt_id": row.get("id"), "action": row.get("action")}


@router.get("/recent")
async def get_recent_attempts(
    limit: int = 50,
    issue_number: int | None = None,
    action: str | None = None,
    _agent: str = Depends(require_agent_loop_key),
):
    db = create_database_client()
    return {
        "attempts": bfs.list_recent_attempts(
            db=db, limit=limit, issue_number=issue_number, action=action
        ),
    }


@router.get("/stats")
async def get_stats(
    hours: int = 168,
    _agent: str = Depends(require_agent_loop_key),
):
    db = create_database_client()
    return bfs.get_attempt_stats(db=db, hours=hours)
