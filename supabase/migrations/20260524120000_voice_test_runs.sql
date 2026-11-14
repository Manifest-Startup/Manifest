-- AI-driven voice-platform testing.
--
-- One row per end-to-end test = (User Simulation Agent generates a case,
-- the platform under test produces a response, the Evaluation Agent
-- scores it). v1 is single-turn, text-only — TTS/STT/multi-turn are
-- reserved for follow-up slices and the schema is shaped so they slot
-- in without an additional migration.
--
-- Owner: backend/app/services/voice_testing_service.py.
-- Architecture: docs/VOICE_TESTING.md.

CREATE TABLE IF NOT EXISTS public.voice_test_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Test-case fields (from User Simulation Agent).
    scenario TEXT NOT NULL
        CHECK (scenario IN ('support_request', 'product_question', 'complaint')),
    user_persona TEXT NOT NULL,
    user_emotion TEXT NOT NULL
        CHECK (user_emotion IN ('neutral', 'confused', 'frustrated', 'angry', 'happy')),
    user_goal TEXT,
    user_input TEXT NOT NULL,
    expected_behavior TEXT,
    success_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,
    failure_conditions JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Execution: the voice platform's response (or a configurable
    -- stub's response for hermetic testing without polluting prod DB).
    assistant_response TEXT,
    executor_kind TEXT NOT NULL DEFAULT 'stub',  -- 'stub' | 'voice_agent'

    -- Evaluation (v1: three scores, 1-5 each).
    score_intent_understanding INT
        CHECK (score_intent_understanding IS NULL OR score_intent_understanding BETWEEN 1 AND 5),
    score_emotional_awareness INT
        CHECK (score_emotional_awareness IS NULL OR score_emotional_awareness BETWEEN 1 AND 5),
    score_helpfulness INT
        CHECK (score_helpfulness IS NULL OR score_helpfulness BETWEEN 1 AND 5),
    overall_score NUMERIC(4, 2),
    pass_status BOOLEAN,             -- pass/fail; null = not yet evaluated

    detected_failures JSONB NOT NULL DEFAULT '[]'::jsonb,
    root_cause_analysis TEXT,
    recommended_fixes JSONB NOT NULL DEFAULT '[]'::jsonb,
    improved_response_example TEXT,

    -- Cost tracking + provenance. Each phase opens its own agent_run.
    simulator_run_id UUID
        REFERENCES public.agent_runs (id) ON DELETE SET NULL,
    executor_run_id UUID
        REFERENCES public.agent_runs (id) ON DELETE SET NULL,
    evaluator_run_id UUID
        REFERENCES public.agent_runs (id) ON DELETE SET NULL,

    triggered_by_user_id UUID
        REFERENCES public.users (user_id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_voice_test_runs_created
    ON public.voice_test_runs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_voice_test_runs_scenario_created
    ON public.voice_test_runs (scenario, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_voice_test_runs_pass_created
    ON public.voice_test_runs (pass_status, created_at DESC)
    WHERE pass_status IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_voice_test_runs_emotion
    ON public.voice_test_runs (user_emotion, pass_status);

COMMENT ON TABLE public.voice_test_runs IS
    'AI-driven voice-platform tests. v1 = single-turn text-only with 5 emotions x 3 scenarios x 3 scores. Multi-turn + TTS/STT reserved for follow-up.';
