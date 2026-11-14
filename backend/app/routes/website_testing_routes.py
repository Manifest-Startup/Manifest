"""Internal website testing API routes for agent-triggered audits."""

from app.routes.dependencies import require_agent_loop_key
from app.services.operations.website_issue_sync import (
    WebsiteIssueSyncConfigurationError,
    website_issue_sync_service,
)
from app.utils.logger import logger
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/api/internal/website-testing", tags=["Internal Agent Loop"], include_in_schema=False
)


class WebsiteIssueSyncRequest(BaseModel):
    target_url: str = Field(
        default="https://manifeststartup.com",
        description="Public URL to audit for the internal Manifest feedback loop.",
    )
    max_pages: int = Field(
        default=6, ge=1, le=20, description="Maximum number of public pages to crawl."
    )
    max_issues: int = Field(
        default=6, ge=1, le=20, description="Maximum number of issue candidates to return."
    )
    create_github_issues: bool = Field(
        default=True,
        description="When true, the service creates GitHub issues directly unless dry_run is also true.",
    )
    dry_run: bool = Field(
        default=False,
        description="When true, generate issue candidates without creating GitHub issues.",
    )
    github_repo: str | None = Field(
        default=None,
        description="Override target repository in owner/name format. Defaults to MANIFEST_GITHUB_REPO.",
    )
    extra_labels: list[str] = Field(
        default_factory=list,
        description="Optional extra GitHub labels to add to every created issue.",
    )


@router.post("/sync-issues")
async def sync_website_issues(
    body: WebsiteIssueSyncRequest,
    _agent: str = Depends(require_agent_loop_key),
):
    """Run the internal Manifest website feedback loop and optionally sync findings to GitHub."""
    try:
        logger.info(
            "[WebsiteTestingRoutes] Starting internal website issue sync for target=%s",
            body.target_url,
        )

        result = await website_issue_sync_service.audit_website_and_sync_issues(
            body.target_url,
            max_pages=body.max_pages,
            max_issues=body.max_issues,
            create_github_issues=body.create_github_issues,
            dry_run=body.dry_run,
            github_repo=body.github_repo,
            extra_labels=body.extra_labels,
        )

        return result
    except ValueError as exc:
        logger.warning("[WebsiteTestingRoutes] Validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WebsiteIssueSyncConfigurationError as exc:
        logger.error("[WebsiteTestingRoutes] Configuration error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("[WebsiteTestingRoutes] Sync failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Website audit failed before issue sync completed."
        ) from exc
