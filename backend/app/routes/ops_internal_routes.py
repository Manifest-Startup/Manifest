"""Internal ops snapshot for dashboards and on-call (agent key only)."""

import os

from app.db.async_pool import get_async_pool_snapshot
from app.db.database import get_db_pool_snapshot
from app.routes.dependencies import require_agent_loop_key
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/internal/ops", tags=["Internal Ops"], include_in_schema=False)


@router.get("/snapshot")
async def ops_snapshot(_agent: str = Depends(require_agent_loop_key)):
    """Return non-sensitive runtime metrics for monitoring (DB pool, config hints).

    Authenticate with the same ``X-Manifest-Agent-Key`` header as other internal
    agent-loop routes (``MANIFEST_AGENT_LOOP_SECRET`` / ``AGENT_LOOP_SECRET``).
    See ``docs/OBSERVABILITY_AND_SLO.md``.
    """
    return {
        "db_pool": get_db_pool_snapshot(),
        "async_db_pool": get_async_pool_snapshot(),
        "graphql_slow_request_threshold_ms": float(os.getenv("GRAPHQL_SLOW_REQUEST_MS", "750")),
        "db_slow_query_threshold_ms": float(os.getenv("DB_SLOW_QUERY_THRESHOLD_MS", "100")),
        "background_job_queue": {
            "status": "not_implemented",
            "note": "Thread-based generation has no queue depth yet; see docs/ASYNC_JOB_QUEUE_DESIGN.md",
        },
    }
