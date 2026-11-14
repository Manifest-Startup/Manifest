"""Generation worker — Phase 3 of the Performance Migration Strategy.

A standalone process (a Render ``type: worker`` service) that drains the
``generation_jobs`` queue: it atomically claims the oldest queued job with
``FOR UPDATE SKIP LOCKED`` (so multiple workers never double-run a job), runs the
requested document generations, and records the result. This is what takes the
10-30s LLM work off the API's request path entirely.

Run it with::

    python -m app.workers.generation_worker

Env:
  WORKER_POLL_INTERVAL_SECONDS  idle poll delay (default 2.0)
  WORKER_ID                     instance id recorded on claimed jobs
                                (default: ``host:pid``)

Safe to deploy before producers enqueue anything — with an empty queue it just
idles. It is intentionally NOT started by the web process.
"""

from __future__ import annotations

import os
import signal
import socket
import time
from collections.abc import Callable
from typing import Any

from app.db.database import create_database_client
from app.services import job_service
from app.utils.logger import logger

# document_type -> generator(description) -> str. Lazy imports keep the heavy
# schema/manifest_manager graph out of module import time.
GENERATORS: dict[str, Callable[[str], str]] = {}


def _load_generators() -> dict[str, Callable[[str], str]]:
    if GENERATORS:
        return GENERATORS
    from app.graphql.schema import (
        _get_pitch_deck,
        _get_product_requirements_document,
        _get_provisional_patent,
    )

    GENERATORS.update(
        {
            "pitch_deck": _get_pitch_deck,
            "product_requirements_document": _get_product_requirements_document,
            "prd": _get_product_requirements_document,
            "provisional_patent": _get_provisional_patent,
            "patent": _get_provisional_patent,
        }
    )
    return GENERATORS


def _worker_id() -> str:
    return os.getenv("WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"


def _idea_description(db: Any, idea_id: str | None) -> str:
    if not idea_id:
        return ""
    resp = db.table("ideas").select("description").eq("idea_id", idea_id).limit(1).execute()
    rows = resp.data or []
    return (rows[0].get("description") if rows else "") or ""


def run_job(db: Any, job: dict[str, Any]) -> dict[str, Any]:
    """Execute every requested document generation for one claimed job."""
    generators = _load_generators()
    description = _idea_description(db, job.get("idea_id"))
    results: dict[str, str] = {}
    for doc_type in job.get("document_types") or []:
        generator = generators.get(doc_type)
        if generator is None:
            logger.warning("[worker] no generator for document_type=%s", doc_type)
            continue
        results[doc_type] = generator(description)
    return results


def process_once(db: Any, worker_id: str) -> bool:
    """Claim and run a single job. Returns True if a job was processed."""
    job = job_service.claim_next_job(db, worker_id)
    if not job:
        return False
    job_id = job["id"]
    logger.info("[worker] claimed job %s (%s)", job_id, job.get("document_types"))
    try:
        results = run_job(db, job)
        job_service.mark_succeeded(db, job_id, results)
        logger.info("[worker] job %s succeeded", job_id)
    except Exception as exc:  # noqa: BLE001 — a bad job must not kill the worker
        logger.error("[worker] job %s failed: %s", job_id, exc)
        job_service.mark_failed(db, job_id, str(exc))
    return True


def main() -> int:
    poll_interval = float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "2.0"))
    worker_id = _worker_id()
    db = create_database_client()
    stopping = {"flag": False}

    def _stop(_signum, _frame):
        logger.info("[worker] shutdown signal received; finishing current loop")
        stopping["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    logger.info("[worker] generation worker started (id=%s, poll=%ss)", worker_id, poll_interval)
    while not stopping["flag"]:
        try:
            did_work = process_once(db, worker_id)
        except Exception as exc:  # noqa: BLE001 — keep the loop alive on transient errors
            logger.error("[worker] poll error: %s", exc)
            did_work = False
        if not did_work:
            time.sleep(poll_interval)
    logger.info("[worker] generation worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
