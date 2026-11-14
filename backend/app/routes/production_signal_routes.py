"""Internal production signal ingest (deduped → GitHub)."""

from app.db.database import create_database_client
from app.routes.dependencies import require_agent_loop_key
from app.services.production_signal_service import production_signal_service
from app.utils.logger import logger
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/api/internal/production-signals", tags=["Internal Agent Loop"], include_in_schema=False
)


class ProductionSignalEvent(BaseModel):
    event_name: str = Field(..., min_length=1, max_length=200)
    route: str | None = Field(default=None, max_length=500)
    severity: str = Field(default="warn", max_length=32)
    error_code: str | None = Field(default=None, max_length=120)
    session_id: str | None = Field(default=None, max_length=128)
    sample: str | None = Field(default=None, max_length=2000)
    create_github_issue: bool = Field(
        default=False,
        description="When true and threshold met, create a deduped GitHub issue (requires GitHub token).",
    )


@router.post("/event")
async def post_production_signal(
    body: ProductionSignalEvent,
    _agent: str = Depends(require_agent_loop_key),
):
    """Ingest a production signal; optionally open GitHub issues when thresholds are met."""
    try:
        db = create_database_client()
        if body.create_github_issue:
            return await production_signal_service.ingest_and_maybe_open_github(
                db,
                event_name=body.event_name,
                route=body.route,
                severity=body.severity,
                error_code=body.error_code,
                session_id=body.session_id,
                sample=body.sample,
                create_github_issue=True,
            )
        return production_signal_service.ingest(
            db,
            event_name=body.event_name,
            route=body.route,
            severity=body.severity,
            error_code=body.error_code,
            session_id=body.session_id,
            sample=body.sample,
        )
    except ValueError as exc:
        logger.warning("[ProductionSignalRoutes] Validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("[ProductionSignalRoutes] Ingest failed: %s", exc)
        raise HTTPException(status_code=502, detail="Production signal ingest failed.") from exc
