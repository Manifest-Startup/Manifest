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
idles. The web process also runs this loop in a background thread
(:func:`start_in_background`, on unless ``GENERATION_WORKER_IN_PROCESS=0``), because
the free Render plan has no worker services; ``FOR UPDATE SKIP LOCKED`` keeps an
extra dedicated worker safe.

Each job runs with the idea owner's own OpenAI key (bring your own key) and saves
the documents onto the idea, exactly like the request-time path.
"""

from __future__ import annotations

import os
import signal
import socket
import time
from collections.abc import Callable
from typing import Any

from app.db.database import create_database_client
from app.services.ideas import generation_jobs as job_service
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


# Job document types -> ideas columns for the single-document generators.
IDEA_COLUMNS = {
    "pitch_deck": "pitch_deck",
    "product_requirements_document": "product_requirements_document",
    "prd": "product_requirements_document",
    "provisional_patent": "provisional_patent",
    "patent": "provisional_patent",
}
# Types produced by the full pipeline (it also refreshes similar ideas and the canvas).
FULL_PIPELINE_TYPES = frozenset({"business_model_canvas", "bmc", "similar_ideas", "all"})


def _owner_key(job: dict[str, Any]) -> str | None:
    """The job owner's own OpenAI key; None falls back to template documents."""
    user_id = job.get("user_id")
    if not user_id:
        return None
    try:
        from app.services.ai.user_keys import load_user_key

        return load_user_key(str(user_id))
    except Exception as exc:  # noqa: BLE001 — a missing key must not fail the job
        logger.warning(
            "[worker] key lookup failed for job %s: %s", job.get("id"), type(exc).__name__
        )
        return None


def run_job(db: Any, job: dict[str, Any]) -> dict[str, Any]:
    """Execute every requested document generation for one claimed job and save it on the idea."""
    from app.services.ai.credentials import use_openai_key
    from app.services.ideas import document_generation

    generators = _load_generators()
    idea_id = job.get("idea_id")
    description = _idea_description(db, idea_id)
    requested = [str(t) for t in job.get("document_types") or []]
    results: dict[str, Any] = {}
    with use_openai_key(_owner_key(job)):
        if FULL_PIPELINE_TYPES.intersection(requested) and idea_id:
            document_generation.generate_background_tasks(description, idea_id)
            results["full_pipeline"] = "saved"
        updates: dict[str, Any] = {}
        for doc_type in requested:
            if doc_type in FULL_PIPELINE_TYPES:
                continue
            generator = generators.get(doc_type)
            if generator is None:
                logger.warning("[worker] no generator for document_type=%s", doc_type)
                results[doc_type] = "unsupported"
                continue
            updates[IDEA_COLUMNS[doc_type]] = generator(description)
            results[doc_type] = "saved"
        if updates and idea_id:
            document_generation._update_idea_documents(
                idea_id, {**updates, "user_id": job.get("user_id")}
            )
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


def run_loop(db: Any, worker_id: str, stop: Any, poll_interval: float) -> None:
    """Drain the queue until ``stop`` (a threading.Event or similar) is set."""
    while not stop.is_set():
        try:
            did_work = process_once(db, worker_id)
        except Exception as exc:  # noqa: BLE001 — keep the loop alive on transient errors
            logger.error("[worker] poll error: %s", exc)
            did_work = False
        if not did_work:
            stop.wait(poll_interval)


_background: dict[str, Any] = {}


def start_in_background() -> bool:
    """Run the worker loop in a daemon thread of the web process (once). Returns True if started."""
    import threading

    if _background or os.getenv("GENERATION_WORKER_IN_PROCESS", "1") == "0":
        return False
    if not os.getenv("DATABASE_URL") or os.getenv("PYTEST_CURRENT_TEST"):
        return False  # in-memory dev database or the test suite: nothing durable to drain
    stop = threading.Event()
    poll_interval = float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "2.0"))
    worker_id = f"{_worker_id()}:web"
    thread = threading.Thread(
        target=run_loop,
        args=(create_database_client(), worker_id, stop, poll_interval),
        name="generation-worker",
        daemon=True,
    )
    _background.update(stop=stop, thread=thread)
    thread.start()
    logger.info("[worker] in-process generation worker started (id=%s)", worker_id)
    return True


def stop_background() -> None:
    stop = _background.get("stop")
    if stop is not None:
        stop.set()


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
