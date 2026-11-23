-- Goals that run (ADR 0020): a person's goal, the dependency-aware plan that reaches it, the
-- approvals a person gives before anything leaves Manifest, the facts Manifest learns along
-- the way (with provenance and confidence) and the event log behind each goal's timeline.
-- Additive: five tables and their indexes. Only the backend reads them (RLS on, no grants).

CREATE TABLE IF NOT EXISTS public.goals (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    idea_id           uuid REFERENCES public.ideas(idea_id) ON DELETE SET NULL,
    title             text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    desired_outcome   text NOT NULL DEFAULT '' CHECK (char_length(desired_outcome) <= 2000),
    success_criteria  jsonb NOT NULL DEFAULT '{}'::jsonb,
    status            text NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active', 'achieved', 'blocked', 'cancelled')),
    source            jsonb NOT NULL DEFAULT '{}'::jsonb,
    version           integer NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS goals_user_updated_idx ON public.goals (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS public.goal_tasks (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id          uuid NOT NULL REFERENCES public.goals(id) ON DELETE CASCADE,
    user_id          uuid NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    step_key         text NOT NULL CHECK (char_length(step_key) BETWEEN 1 AND 60),
    position         integer NOT NULL DEFAULT 0,
    title            text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    capability       text NOT NULL,
    risk_tier        smallint NOT NULL CHECK (risk_tier BETWEEN 0 AND 3),
    status           text NOT NULL DEFAULT 'proposed'
                     CHECK (status IN ('proposed', 'ready', 'awaiting_authorization', 'running',
                                       'waiting_external', 'blocked', 'completed', 'failed',
                                       'cancelled')),
    depends_on       text[] NOT NULL DEFAULT '{}',
    input            jsonb NOT NULL DEFAULT '{}'::jsonb,
    result           jsonb NOT NULL DEFAULT '{}'::jsonb,
    verification     jsonb NOT NULL DEFAULT '{}'::jsonb,
    attempts         integer NOT NULL DEFAULT 0,
    last_error       text,
    next_check_at    timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT goal_tasks_goal_step_key UNIQUE (goal_id, step_key)
);
CREATE INDEX IF NOT EXISTS goal_tasks_goal_idx ON public.goal_tasks (goal_id, position);
CREATE INDEX IF NOT EXISTS goal_tasks_waiting_idx
    ON public.goal_tasks (next_check_at) WHERE status = 'waiting_external';

CREATE TABLE IF NOT EXISTS public.approval_requests (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    goal_id       uuid NOT NULL REFERENCES public.goals(id) ON DELETE CASCADE,
    task_id       uuid NOT NULL REFERENCES public.goal_tasks(id) ON DELETE CASCADE,
    action        text NOT NULL,
    summary       text NOT NULL,
    reason        text NOT NULL,
    consequences  text NOT NULL,
    risk_tier     smallint NOT NULL CHECK (risk_tier BETWEEN 0 AND 3),
    scope         jsonb NOT NULL,
    scope_sha256  text NOT NULL,
    status        text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'denied', 'expired', 'superseded')),
    decided_via   text,
    expires_at    timestamptz NOT NULL,
    decided_at    timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS approval_requests_user_status_idx
    ON public.approval_requests (user_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS approval_requests_one_pending_per_task
    ON public.approval_requests (task_id) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS public.knowledge_facts (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    goal_id         uuid REFERENCES public.goals(id) ON DELETE SET NULL,
    subject_type    text NOT NULL,
    subject_key     text NOT NULL CHECK (char_length(subject_key) BETWEEN 1 AND 200),
    predicate       text NOT NULL CHECK (char_length(predicate) BETWEEN 1 AND 80),
    object_type     text NOT NULL,
    object_value    text NOT NULL CHECK (char_length(object_value) BETWEEN 1 AND 2000),
    kind            text NOT NULL
                    CHECK (kind IN ('stated_by_user', 'verified', 'external_claim', 'inferred')),
    confidence      real NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    source_type     text NOT NULL,
    source_ref      text NOT NULL,
    source_at       timestamptz,
    extraction      text NOT NULL,
    status          text NOT NULL DEFAULT 'current' CHECK (status IN ('current', 'superseded')),
    superseded_by   uuid REFERENCES public.knowledge_facts(id) ON DELETE SET NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS knowledge_facts_subject_idx
    ON public.knowledge_facts (user_id, subject_type, subject_key, status);
CREATE INDEX IF NOT EXISTS knowledge_facts_goal_idx ON public.knowledge_facts (goal_id);

CREATE TABLE IF NOT EXISTS public.goal_events (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    goal_id     uuid REFERENCES public.goals(id) ON DELETE CASCADE,
    type        text NOT NULL,
    summary     text NOT NULL,
    payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
    dedupe_key  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS goal_events_goal_idx ON public.goal_events (goal_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS goal_events_dedupe_key
    ON public.goal_events (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL;

ALTER TABLE public.goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.goal_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.approval_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.goal_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON public.goals, public.goal_tasks, public.approval_requests,
    public.knowledge_facts, public.goal_events FROM anon, authenticated, service_role;
