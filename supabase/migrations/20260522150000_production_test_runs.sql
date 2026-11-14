-- Continuous production-test results, posted by Playwright + other
-- smoke runners via POST /api/internal/production-tests/results.
-- Owned by backend/app/services/production_test_service.py.
-- Architecture: docs/PRODUCTION_TESTING.md

CREATE TABLE IF NOT EXISTS public.production_test_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    -- Identifies the test instance: e.g. "auth.login@chromium",
    -- "ideas.create@firefox". Used as the dedupe key into open GitHub
    -- issues (alongside the first line of error_message).
    test_name TEXT NOT NULL,
    suite TEXT,
    environment TEXT NOT NULL DEFAULT 'production',
    -- 'pass' / 'fail' / 'flaky' / 'error'.  'flaky' is reserved for the
    -- retry-passed-second-attempt case Playwright surfaces.
    status TEXT NOT NULL CHECK (status IN ('pass', 'fail', 'flaky', 'error', 'skipped')),
    severity TEXT NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('low', 'medium', 'high')),

    error_message TEXT,
    stack_trace TEXT,

    -- Optional captured artifacts. These are URLs (e.g. a CI artifact
    -- link or a public-bucket path); content is never stored inline.
    screenshot_url TEXT,
    video_url TEXT,
    har_url TEXT,
    console_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    network_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    suspected_files JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- CI traceability.
    git_sha TEXT,
    git_ref TEXT,
    ci_run_url TEXT,
    runner TEXT,
    duration_ms INT,

    -- Link to the deduped GitHub issue created from this failure
    -- (NULL on pass; NULL on fail if dedupe matched an existing open
    -- issue — see `linked_existing_issue_url`).
    github_issue_number INT,
    github_issue_url TEXT,
    linked_existing_issue_url TEXT,

    -- Free-form context (test runner version, browser, etc.).
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prod_test_runs_started
    ON public.production_test_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_prod_test_runs_status_started
    ON public.production_test_runs (status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_prod_test_runs_test_status
    ON public.production_test_runs (test_name, status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_prod_test_runs_failures_recent
    ON public.production_test_runs (started_at DESC)
    WHERE status IN ('fail', 'error');

COMMENT ON TABLE public.production_test_runs IS
    'One row per individual production smoke-test execution. Failures are deduped against open GitHub issues and (optionally) auto-filed via GitHubIssueService.';
