"""Tests for the Phase 3 generation-job persistence/lifecycle layer.

Exercises create (+ idempotency dedup), read, and status transitions against
the in-memory DB. The SKIP-LOCKED claim is integration-only (real Postgres) and
not covered here.
"""

from __future__ import annotations

import pytest
from app.db.database import InMemoryDatabaseClient
from app.services import job_service as js


@pytest.fixture
def db():
    return InMemoryDatabaseClient()


def test_create_job_returns_queued_with_id(db):
    job = js.create_job(db, user_id="u1", idea_id="i1", document_types=["pitch_deck", "prd"])
    assert job["id"]
    assert job["status"] == js.STATUS_QUEUED
    assert job["document_types"] == ["pitch_deck", "prd"]
    assert job["attempt_count"] == 0


def test_get_job_roundtrip(db):
    job = js.create_job(db, user_id="u1", idea_id="i1", document_types=["pitch_deck"])
    fetched = js.get_job(db, job["id"])
    assert fetched is not None
    assert fetched["id"] == job["id"]


def test_get_job_missing_returns_none(db):
    assert js.get_job(db, "does-not-exist") is None


def test_idempotency_dedupes_active_job(db):
    first = js.create_job(
        db, user_id="u1", idea_id="i1", document_types=["pitch_deck"], idempotency_key="key-1"
    )
    second = js.create_job(
        db, user_id="u1", idea_id="i1", document_types=["pitch_deck"], idempotency_key="key-1"
    )
    # Same active job returned, not a duplicate.
    assert second["id"] == first["id"]


def test_idempotency_key_reusable_after_terminal(db):
    first = js.create_job(
        db, user_id="u1", idea_id="i1", document_types=["pitch_deck"], idempotency_key="key-2"
    )
    js.mark_succeeded(db, first["id"], {"ok": True})
    # The key is free again once the first job is no longer active.
    second = js.create_job(
        db, user_id="u1", idea_id="i1", document_types=["pitch_deck"], idempotency_key="key-2"
    )
    assert second["id"] != first["id"]
    assert second["status"] == js.STATUS_QUEUED


def test_no_idempotency_key_always_creates(db):
    a = js.create_job(db, user_id="u1", idea_id="i1", document_types=["prd"])
    b = js.create_job(db, user_id="u1", idea_id="i1", document_types=["prd"])
    assert a["id"] != b["id"]


def test_mark_running_then_succeeded(db):
    job = js.create_job(db, user_id="u1", idea_id="i1", document_types=["pitch_deck"])
    js.mark_running(db, job["id"], worker_id="worker-A")
    running = js.get_job(db, job["id"])
    assert running["status"] == js.STATUS_RUNNING
    assert running["locked_by"] == "worker-A"

    js.mark_succeeded(db, job["id"], {"pitch_deck": "..."})
    done = js.get_job(db, job["id"])
    assert done["status"] == js.STATUS_SUCCEEDED
    assert done["result"] == {"pitch_deck": "..."}


def test_mark_failed_truncates_error(db):
    job = js.create_job(db, user_id="u1", idea_id="i1", document_types=["pitch_deck"])
    js.mark_failed(db, job["id"], "boom " * 1000)
    failed = js.get_job(db, job["id"])
    assert failed["status"] == js.STATUS_FAILED
    assert len(failed["error_message"]) <= 2000


def test_find_active_by_idempotency(db):
    assert js.find_active_by_idempotency(db, "") is None
    assert js.find_active_by_idempotency(db, "missing") is None
    job = js.create_job(
        db, user_id="u1", idea_id="i1", document_types=["prd"], idempotency_key="k9"
    )
    found = js.find_active_by_idempotency(db, "k9")
    assert found is not None and found["id"] == job["id"]
