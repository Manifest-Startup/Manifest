# Async job queue design (background generation and REST generate)

Last updated **May 3, 2026**.

Manifest today starts heavy work from **GraphQL** (`runBackgroundTasks`) and **threads** inside the API process ([docs/ARCHITECTURE_REFERENCE.md](ARCHITECTURE_REFERENCE.md)). `POST /api/v1/ideas/{idea_id}/generate` runs **synchronously** and is documented as a latency hotspot ([docs/API.md](API.md)). This document specifies a **target** queue-based design for performance and horizontal scalability.

## Objectives

1. Move LLM and document generation off the interactive request path.
2. Support **horizontal scaling** of API workers without duplicate concurrent generation for the same logical job.
3. Offer a **status API** for the web app and for `/api/v1` clients (polling or webhooks later).

## Job identity and idempotency

- **Idempotency key**: client-supplied header `Idempotency-Key` (UUID recommended) or derived hash of `(user_id, idea_id, document_types[], logical_version)`.
- **Dedup**: unique partial index on `(idempotency_key)` where status in (`queued`, `running`) OR completed within a short TTL if you want “return same result” semantics.
- **Job id**: server-generated UUID primary key returned immediately to callers.

## Proposed persistence (Postgres)

Table `generation_jobs` (name illustrative):

| Column | Type | Notes |
|--------|------|--------|
| id | uuid | Primary key returned to client |
| user_id | uuid | Owner |
| idea_id | uuid | Target idea |
| document_types | text[] | e.g. `pitch_deck`, `prd` |
| status | text | `queued`, `running`, `succeeded`, `failed`, `cancelled` |
| idempotency_key | text | Nullable; unique when set |
| attempt_count | int | Retries |
| locked_at | timestamptz | Worker lease |
| locked_by | text | Worker instance id |
| error_message | text | Sanitized failure |
| created_at / updated_at | timestamptz | |

Optional `generation_job_events` for audit trail.

## API shapes

### GraphQL (app)

- Mutation `enqueueBackgroundTasks(ideaId, documentTypes, idempotencyKey)` → `{ jobId, status }` instead of fire-and-forget boolean (or keep legacy mutation and add the new one during transition).
- Query `generationJob(jobId)` → status, per-document progress, errors.

### REST (`/api/v1`)

- `POST /api/v1/ideas/{idea_id}/generate` → **202 Accepted** with `{ "job_id": "...", "status": "queued" }` when async mode is on (feature flag or `Prefer: respond-async` style header).
- `GET /api/v1/jobs/{job_id}` → status payload for polling.

Document breaking changes in [docs/API.md](API.md) when implemented.

## Worker process

- Separate deployable or a **dedicated worker dyno** that polls `generation_jobs` with `FOR UPDATE SKIP LOCKED` (or uses a transactional outbox pattern).
- Concurrency limits per worker and global fair-share per `user_id` / API key to protect shared LLM quotas.
- On success: write artifacts to DB as today; optionally enqueue **object storage upload** per [docs/MEDIA_OBJECT_STORAGE_MIGRATION.md](MEDIA_OBJECT_STORAGE_MIGRATION.md).

## Observability

- Metrics: queue depth, oldest `queued` age, success/fail counts, LLM latency by job type.
- Tie into [docs/OBSERVABILITY_AND_SLO.md](OBSERVABILITY_AND_SLO.md) once `background_job_queue` is populated in `GET /api/internal/ops/snapshot`.

## Rollout

1. Add tables and worker loop reading jobs that no producer enqueues yet.
2. Dual-path: GraphQL mutation enqueues **and** starts current thread (behind flag); verify worker completion.
3. Default new clients to async; keep sync fallback for a deprecation window.
4. Remove thread path when stable.
