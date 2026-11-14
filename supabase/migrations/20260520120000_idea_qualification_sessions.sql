-- Conversational pre-build qualification of users and their startup ideas.
-- Owned by backend/app/services/idea_qualification_service.py and the
-- startIdeaQualification / continueIdeaQualification GraphQL mutations.

CREATE TABLE IF NOT EXISTS public.idea_qualification_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users (user_id) ON DELETE CASCADE,
    idea_id UUID REFERENCES public.ideas (idea_id) ON DELETE SET NULL,
    initial_idea_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_progress'
        CHECK (status IN ('in_progress', 'complete', 'abandoned')),

    user_seriousness INT,
    user_domain_knowledge INT,
    user_goals TEXT,
    user_budget TEXT,
    user_timeline TEXT,
    user_execution_ability INT,

    idea_market_need INT,
    idea_target_customer TEXT,
    idea_feasibility INT,
    idea_defensibility INT,
    idea_revenue_potential INT,
    idea_competition TEXT,
    idea_risks TEXT,

    qualification_score INT,
    qualification_explanation TEXT,

    transcript JSONB NOT NULL DEFAULT '[]'::jsonb,
    next_question TEXT,
    turn_count INT NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_idea_qualification_sessions_user
    ON public.idea_qualification_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_idea_qualification_sessions_user_status
    ON public.idea_qualification_sessions (user_id, status);

COMMENT ON TABLE public.idea_qualification_sessions IS
    'Multi-turn agent qualifying user seriousness + idea quality before BMC generation.';
