-- Restore schema the backend uses but production never had (found 2026-11-18 while testing
-- the agent plugin, ADR 0004). Additive only: nothing is dropped, renamed or rewritten.
--
-- * ideas.is_published: every idea list, detail, search and publish query selects it, so
--   opening an idea and universal search failed. Production's `visibility` column is unused
--   and NULL for every row, so there is nothing to backfill.
-- * user_sessions: sessions.py, SCIM deprovisioning, DSAR and tenant purge. Without it every
--   session check failed open, so signing out or revoking a session (browser, CLI, agent)
--   had no effect.
-- * idea_collaborators: collaboration.py and the GraphQL collaboration fields.
-- * rate_limit_events: shared/rate_limit.py. Without it every rate limit failed open.
-- * intellectual_properties(idea_id) unique: document_generation.py upserts ON CONFLICT (idea_id).
--
-- The backend reaches these tables through its private DATABASE_URL as the owner, so RLS is
-- on with no policies and the PostgREST roles get nothing (20261114090000 lockdown).

ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS is_published boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_ideas_published_created
    ON public.ideas (created_at DESC) WHERE is_published;

CREATE TABLE IF NOT EXISTS public.user_sessions (
    session_id   uuid PRIMARY KEY,
    user_id      uuid NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    created_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL,
    revoked_at   timestamptz,
    last_seen_at timestamptz DEFAULT now(),
    request_ip   text,
    user_agent   text
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_active
    ON public.user_sessions (user_id, expires_at) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS public.idea_collaborators (
    collaborator_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idea_id         uuid NOT NULL REFERENCES public.ideas(idea_id) ON DELETE CASCADE,
    user_id         uuid NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    role            text NOT NULL DEFAULT 'viewer'
                    CHECK (role IN ('owner', 'editor', 'commenter', 'viewer')),
    invited_by      uuid REFERENCES public.users(user_id) ON DELETE SET NULL,
    invited_at      timestamptz DEFAULT now(),
    status          text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'accepted', 'declined')),
    accepted_at     timestamptz,
    CONSTRAINT idea_collaborators_idea_user_key UNIQUE (idea_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_idea_collaborators_user_status
    ON public.idea_collaborators (user_id, status);

CREATE TABLE IF NOT EXISTS public.rate_limit_events (
    id              bigserial PRIMARY KEY,
    bucket_hash     text NOT NULL,
    bucket_key_hint text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_limit_events_bucket
    ON public.rate_limit_events (bucket_hash, created_at);
CREATE INDEX IF NOT EXISTS idx_rate_limit_events_expires
    ON public.rate_limit_events (expires_at);

CREATE UNIQUE INDEX IF NOT EXISTS intellectual_properties_idea_id_key
    ON public.intellectual_properties (idea_id);

ALTER TABLE public.user_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.idea_collaborators ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rate_limit_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON public.user_sessions, public.idea_collaborators, public.rate_limit_events
    FROM anon, authenticated, service_role;
REVOKE ALL PRIVILEGES ON SEQUENCE public.rate_limit_events_id_seq FROM anon, authenticated, service_role;
