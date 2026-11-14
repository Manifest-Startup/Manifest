"""Generation-job persistence + status — Phase 3 of the Performance Migration
Strategy (see docs/ASYNC_JOB_QUEUE_DESIGN.md).

Heavy LLM/document generation moves off the interactive request path onto the
durable ``generation_jobs`` table. A producer calls :func:`create_job` (returning
a job id immediately); a dedicated worker drains the queue with
:func:`claim_next_job` (``FOR UPDATE SKIP LOCKED``) and marks the result. Clients
poll :func:`get_job`.

This module is the persistence + lifecycle layer only — it does not itself run
generation, so it is safe to ship before the worker is deployed and before any
producer is rewired. The lifecycle functions use the Supabase-style query API
and are unit-tested against the in-memory DB; the SKIP-LOCKED claim uses raw SQL
and runs against real Postgres in the worker.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

JOB_TABLE = "generation_jobs"

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)
TERMINAL_STATUSES = (STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_active_by_idempotency(db: Any, idempotency_key: str) -> dict[str, Any] | None:
    """Return the in-flight (queued/running) job for an idempotency key, if any."""
    if not idempotency_key:
        return None
    resp = (
        db.table(JOB_TABLE)
        .select("*")
        .eq("idempotency_key", idempotency_key)
        .in_("status", list(ACTIVE_STATUSES))
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def create_job(
    db: Any,
    *,
    user_id: str | None,
    idea_id: str | None,
    document_types: list[str],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Enqueue a generation job and return it.

    If ``idempotency_key`` is given and an active job already exists for it, that
    existing job is returned instead of creating a duplicate — so a retried
    request joins the in-flight generation rather than starting a second one.
    """
    if idempotency_key:
        existing = find_active_by_idempotency(db, idempotency_key)
        if existing is not None:
            return existing

    job = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "idea_id": idea_id,
        "document_types": list(document_types or []),
        "status": STATUS_QUEUED,
        "idempotency_key": idempotency_key,
        "attempt_count": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    db.table(JOB_TABLE).insert(job).execute()
    return job


def get_job(db: Any, job_id: str) -> dict[str, Any] | None:
    """Fetch a job by id (the status-API read)."""
    resp = db.table(JOB_TABLE).select("*").eq("id", job_id).limit(1).execute()
    rows = resp.data or []
    return rows[0] if rows else None


def _update(db: Any, job_id: str, updates: dict[str, Any]) -> None:
    updates = {**updates, "updated_at": _now_iso()}
    db.table(JOB_TABLE).update(updates).eq("id", job_id).execute()


def mark_running(db: Any, job_id: str, worker_id: str) -> None:
    _update(
        db,
        job_id,
        {"status": STATUS_RUNNING, "locked_at": _now_iso(), "locked_by": worker_id},
    )


def mark_succeeded(db: Any, job_id: str, result: dict[str, Any] | None = None) -> None:
    _update(db, job_id, {"status": STATUS_SUCCEEDED, "result": result, "error_message": None})


def mark_failed(db: Any, job_id: str, error_message: str) -> None:
    # Truncate so a verbose stack trace can't bloat the row.
    _update(db, job_id, {"status": STATUS_FAILED, "error_message": (error_message or "")[:2000]})


# Raw SQL for the worker — atomic claim of the oldest queued job. Concurrent
# workers never grab the same row thanks to FOR UPDATE SKIP LOCKED. Not used by
# the in-memory client (no row locking), so it is exercised against real
# Postgres in the worker, not in unit tests.
_CLAIM_SQL = """
UPDATE generation_jobs
SET status = 'running',
    locked_at = now(),
    locked_by = %s,
    attempt_count = attempt_count + 1,
    updated_at = now()
WHERE id = (
    SELECT id FROM generation_jobs
    WHERE status = 'queued'
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING *;
"""


def claim_next_job(db: Any, worker_id: str) -> dict[str, Any] | None:
    """Atomically claim the oldest queued job for this worker (or None)."""
    resp = db.execute_raw(_CLAIM_SQL, (worker_id,))
    rows = getattr(resp, "data", None) or []
    return rows[0] if rows else None
