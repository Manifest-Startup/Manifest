-- Stage #3: workspace ideas list hot path (migration roadmap #215)
-- - Index for per-user list ordered by recency
-- - Denormalized list metadata so GraphQL list queries avoid reading multi-MB document blobs

CREATE INDEX IF NOT EXISTS idx_ideas_user_id_created_at
    ON public.ideas (user_id, created_at DESC);

ALTER TABLE public.ideas
    ADD COLUMN IF NOT EXISTS generated_asset_count smallint NOT NULL DEFAULT 0;

ALTER TABLE public.ideas
    ADD COLUMN IF NOT EXISTS has_description boolean NOT NULL DEFAULT false;

-- One-time backfill for existing rows (safe to re-run)
UPDATE public.ideas
SET
    has_description = COALESCE(TRIM(description), '') <> '',
    generated_asset_count = (
        CASE WHEN COALESCE(TRIM(pitch_deck), '') <> '' THEN 1 ELSE 0 END
        + CASE WHEN COALESCE(TRIM(product_requirements_document), '') <> '' THEN 1 ELSE 0 END
        + CASE WHEN COALESCE(TRIM(provisional_patent), '') <> '' THEN 1 ELSE 0 END
        + CASE WHEN COALESCE(TRIM(business_model_canvas), '') <> '' THEN 1 ELSE 0 END
    );
