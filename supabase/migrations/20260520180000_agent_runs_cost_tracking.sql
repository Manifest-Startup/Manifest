-- Agent run + cost tracking foundation.
-- Backend owner: app/services/cost_tracking_service.py
-- Architecture: docs/COST_TRACKING.md

-- A single execution of an agent (e.g. one qualification session, one
-- BMC regeneration, one pitch-deck build). Aggregates token + cost
-- totals so the dashboard doesn't have to scan the cost-event table.
CREATE TABLE IF NOT EXISTS public.agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users (user_id) ON DELETE CASCADE,
    agent_kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'complete', 'failed', 'cancelled')),
    idea_id UUID REFERENCES public.ideas (idea_id) ON DELETE SET NULL,
    qualification_session_id UUID
        REFERENCES public.idea_qualification_sessions (id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    total_model_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    total_external_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    total_billable_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    total_input_tokens INT NOT NULL DEFAULT 0,
    total_output_tokens INT NOT NULL DEFAULT 0,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_user_started
    ON public.agent_runs (user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_kind_started
    ON public.agent_runs (agent_kind, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status
    ON public.agent_runs (status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_qualification_session
    ON public.agent_runs (qualification_session_id)
    WHERE qualification_session_id IS NOT NULL;

-- Optional sub-steps inside a run. Useful when one agent run fans out
-- (e.g. BMC: nine section tasks under one run).
CREATE TABLE IF NOT EXISTS public.agent_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES public.agent_runs (id) ON DELETE CASCADE,
    task_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'complete', 'failed', 'skipped')),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_run ON public.agent_tasks (run_id);

-- One row per billable LLM/external API call. The user_id column is
-- denormalized for fast monthly-spend queries without joining runs.
CREATE TABLE IF NOT EXISTS public.agent_cost_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users (user_id) ON DELETE CASCADE,
    run_id UUID REFERENCES public.agent_runs (id) ON DELETE CASCADE,
    task_id UUID REFERENCES public.agent_tasks (id) ON DELETE SET NULL,
    agent_kind TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    cached_input_tokens INT NOT NULL DEFAULT 0,
    model_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    external_api_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    billable_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cost_events_user_time
    ON public.agent_cost_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cost_events_run
    ON public.agent_cost_events (run_id);
CREATE INDEX IF NOT EXISTS idx_cost_events_kind_time
    ON public.agent_cost_events (agent_kind, created_at DESC);

-- Per-user variable-cost cap and billing prefs. One row per user is
-- created lazily on first read; defaults live in code so we can change
-- them without a migration.
CREATE TABLE IF NOT EXISTS public.user_cost_limits (
    user_id UUID PRIMARY KEY REFERENCES public.users (user_id) ON DELETE CASCADE,
    monthly_variable_cap_usd NUMERIC(10, 2) NOT NULL DEFAULT 25.00,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    base_subscription_usd NUMERIC(10, 2) NOT NULL DEFAULT 49.99,
    currency TEXT NOT NULL DEFAULT 'USD',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.agent_runs IS
    'One row per agent execution. Aggregates totals so the user/admin dashboards skip the cost_events scan.';
COMMENT ON TABLE public.agent_cost_events IS
    'Per LLM/external call billable event. user_id is denormalized for fast monthly-spend queries.';
COMMENT ON TABLE public.user_cost_limits IS
    'Per-user variable spend cap + pause flag. Server-side enforcement gate ships in a follow-up.';
