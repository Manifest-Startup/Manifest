-- Per-idea partner candidates produced by the partner-discovery agent.
-- One row per (idea_id, candidate name). The agent ranks and writes
-- candidates; the user reviews and optionally approves for downstream
-- integration / outreach. v1 = discovery + approval flag only — actual
-- outreach is gated behind explicit user action that does NOT live in
-- this slice (spec: "do not contact partners or send data externally
-- without user approval").
--
-- Owner: backend/app/services/partner_discovery_service.py.
-- Architecture: docs/PARTNER_DISCOVERY.md.

CREATE TABLE IF NOT EXISTS public.partner_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idea_id UUID NOT NULL REFERENCES public.ideas (idea_id) ON DELETE CASCADE,

    -- Display fields.
    name TEXT NOT NULL,
    website TEXT,
    category TEXT NOT NULL,
    why_relevant TEXT,
    suggested_use TEXT,

    -- Integration metadata (per spec section "Partner output format").
    integration_type TEXT NOT NULL
        CHECK (integration_type IN ('api', 'mcp', 'sdk', 'webhook', 'zapier', 'manual', 'unknown')),
    data_required TEXT,
    actions_possible TEXT,
    pricing_notes TEXT,
    risk_notes TEXT,
    implementation_difficulty TEXT
        CHECK (implementation_difficulty IS NULL OR implementation_difficulty IN ('low', 'medium', 'high')),
    recommended_next_step TEXT,

    -- Ranking + dedupe.
    rank INT NOT NULL DEFAULT 999,
    relevance_score INT
        CHECK (relevance_score IS NULL OR (relevance_score BETWEEN 0 AND 100)),
    confidence TEXT
        CHECK (confidence IS NULL OR confidence IN ('low', 'medium', 'high')),

    -- Approval flag. v1 just records the user's intent; the future
    -- outreach agent will read approved=true rows. NO external calls
    -- happen as a side-effect of flipping this flag.
    approved BOOLEAN NOT NULL DEFAULT FALSE,
    approved_at TIMESTAMPTZ,
    approved_by UUID REFERENCES public.users (user_id) ON DELETE SET NULL,

    -- Provenance.
    generated_by_run_id UUID
        REFERENCES public.agent_runs (id) ON DELETE SET NULL,
    last_generated_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- One row per (idea_id, lowercased name) so repeat discovery
    -- runs update existing candidates instead of duplicating them.
    CONSTRAINT partner_candidates_uniq
        UNIQUE (idea_id, name)
);

CREATE INDEX IF NOT EXISTS idx_partner_candidates_idea_rank
    ON public.partner_candidates (idea_id, rank);
CREATE INDEX IF NOT EXISTS idx_partner_candidates_idea_approved
    ON public.partner_candidates (idea_id)
    WHERE approved = TRUE;
CREATE INDEX IF NOT EXISTS idx_partner_candidates_run
    ON public.partner_candidates (generated_by_run_id)
    WHERE generated_by_run_id IS NOT NULL;

COMMENT ON TABLE public.partner_candidates IS
    'Per-idea partner suggestions from the LLM-backed partner-discovery agent. Approval flag is internal-only in v1 — no external outreach happens automatically.';
