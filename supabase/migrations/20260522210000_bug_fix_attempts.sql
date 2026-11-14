-- Diagnose-only bug-fix agent: one row per attempt against a labeled
-- GitHub issue. v1 just posts a diagnosis comment to the issue and
-- records the attempt here. v2 will extend with branch + draft PR
-- fields (already in the schema below as nullable).
--
-- Owned by backend/app/services/bug_fix_service.py.
-- Architecture: docs/BUG_FIX_AGENT.md.

CREATE TABLE IF NOT EXISTS public.bug_fix_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    github_issue_number INT NOT NULL,
    github_issue_url TEXT,
    issue_title TEXT,

    source_environment TEXT,

    source_test_run_id UUID
        REFERENCES public.production_test_runs (id) ON DELETE SET NULL,

    action TEXT NOT NULL
        CHECK (action IN (
            'diagnosis_posted',
            'declined',
            'draft_pr_opened',     -- v2
            'draft_pr_updated',    -- v2
            'failed'
        )),

    confidence TEXT
        CHECK (confidence IS NULL OR confidence IN ('low', 'medium', 'high')),

    diagnosis_markdown TEXT,
    risks JSONB NOT NULL DEFAULT '[]'::jsonb,
    suspected_files JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- v2 reserved fields.
    branch_name TEXT,
    draft_pr_number INT,
    draft_pr_url TEXT,

    -- LLM accounting.
    model TEXT,
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    model_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,

    error_message TEXT,
    runner TEXT,
    ci_run_url TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bug_fix_attempts_issue
    ON public.bug_fix_attempts (github_issue_number);
CREATE INDEX IF NOT EXISTS idx_bug_fix_attempts_created
    ON public.bug_fix_attempts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bug_fix_attempts_action_created
    ON public.bug_fix_attempts (action, created_at DESC);

COMMENT ON TABLE public.bug_fix_attempts IS
    'One row per autonomous bug-fix attempt. v1 = diagnose-only (comment posted to issue). v2 will extend with draft-PR fields.';
