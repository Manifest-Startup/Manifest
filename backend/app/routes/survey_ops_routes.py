"""Internal survey analytics and GitHub triage routes."""

from app.db.database import create_database_client
from app.routes.dependencies import require_agent_loop_key
from app.services.operations.survey_ops import SurveyOpsConfigurationError, survey_ops_service
from app.utils.logger import logger
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/api/internal/survey-ops", tags=["Internal Agent Loop"], include_in_schema=False
)


class SurveySummaryRequest(BaseModel):
    window_days: int = Field(
        default=90, ge=7, le=365, description="Rolling time window to summarize."
    )
    include_issue_candidates: bool = Field(
        default=False,
        description="When true, also generate GitHub-ready issue candidates from recurring survey signals.",
    )
    max_issues: int = Field(
        default=6, ge=1, le=20, description="Maximum number of issue candidates to include."
    )
    min_theme_count: int = Field(
        default=2,
        ge=1,
        le=25,
        description="Minimum recurring count before an issue candidate is emitted.",
    )


class SurveyIssueSyncRequest(BaseModel):
    window_days: int = Field(
        default=90, ge=7, le=365, description="Rolling time window to inspect."
    )
    max_issues: int = Field(
        default=6, ge=1, le=20, description="Maximum number of GitHub-ready issue candidates."
    )
    min_theme_count: int = Field(
        default=2,
        ge=1,
        le=25,
        description="Minimum recurring count before an issue candidate is emitted.",
    )
    create_github_issues: bool = Field(
        default=True,
        description="When true, create GitHub issues directly unless dry_run is also true.",
    )
    dry_run: bool = Field(
        default=False,
        description="When true, return the issue candidates without creating GitHub issues.",
    )
    github_repo: str | None = Field(
        default=None,
        description="Override target repository in owner/name format. Defaults to MANIFEST_GITHUB_REPO or the service fallback.",
    )
    extra_labels: list[str] = Field(
        default_factory=list,
        description="Optional extra GitHub labels to apply to every created issue.",
    )


@router.post("/summary")
async def get_survey_summary(
    body: SurveySummaryRequest,
    _agent: str = Depends(require_agent_loop_key),
):
    """Return aggregate survey insights for internal product and research analysis."""
    try:
        db = create_database_client()
        return survey_ops_service.get_summary(
            db,
            window_days=body.window_days,
            include_issue_candidates=body.include_issue_candidates,
            max_issues=body.max_issues,
            min_theme_count=body.min_theme_count,
        )
    except ValueError as exc:
        logger.warning("[SurveyOpsRoutes] Validation error while building survey summary: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("[SurveyOpsRoutes] Survey summary failed: %s", exc)
        raise HTTPException(status_code=502, detail="Survey summary failed.") from exc


@router.post("/sync-issues")
async def sync_survey_issues(
    body: SurveyIssueSyncRequest,
    _agent: str = Depends(require_agent_loop_key),
):
    """Generate recurring survey issue candidates and optionally create GitHub issues."""
    try:
        db = create_database_client()
        return await survey_ops_service.sync_issues(
            db,
            window_days=body.window_days,
            max_issues=body.max_issues,
            min_theme_count=body.min_theme_count,
            create_github_issues=body.create_github_issues,
            dry_run=body.dry_run,
            github_repo=body.github_repo,
            extra_labels=body.extra_labels,
        )
    except ValueError as exc:
        logger.warning("[SurveyOpsRoutes] Validation error while syncing survey issues: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SurveyOpsConfigurationError as exc:
        logger.error("[SurveyOpsRoutes] Configuration error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("[SurveyOpsRoutes] Survey issue sync failed: %s", exc)
        raise HTTPException(status_code=502, detail="Survey issue sync failed.") from exc
