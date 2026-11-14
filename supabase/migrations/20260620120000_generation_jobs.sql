-- Phase 3 of the Performance Migration Strategy: move heavy LLM/document
-- generation off the interactive request path onto a durable queue that a
-- dedicated worker drains with FOR UPDATE SKIP LOCKED. Per
-- docs/ASYNC_JOB_QUEUE_DESIGN.md. Additive only — no existing path changes
-- until producers enqueue and the worker is deployed.

CREATE TABLE IF NOT EXISTS generation_jobs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid,
    idea_id         uuid,
    document_types  text[] NOT NULL DEFAULT '{}',
    status          text NOT NULL DEFAULT 'queued',
    idempotency_key text,
    attempt_count   int NOT NULL DEFAULT 0,
    locked_at       timestamptz,
    locked_by       text,
    error_message   text,
    result          jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT generation_jobs_status_check
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled'))
);

-- Worker poll order: oldest queued job first.
CREATE INDEX IF NOT EXISTS idx_generation_jobs_status_created
    ON generation_jobs (status, created_at);

-- Owner lookups for the status API.
CREATE INDEX IF NOT EXISTS idx_generation_jobs_user
    ON generation_jobs (user_id, created_at DESC);

-- Idempotency: at most one active job per key (lets a retried request return
-- the in-flight job instead of starting a duplicate generation).
CREATE UNIQUE INDEX IF NOT EXISTS uq_generation_jobs_active_idempotency
    ON generation_jobs (idempotency_key)
    WHERE idempotency_key IS NOT NULL AND status IN ('queued', 'running');
