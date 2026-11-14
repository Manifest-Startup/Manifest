-- Keep document blobs on ideas compatible with the production schema and the
-- list metadata backfill that follows in 20260523180000_ideas_list_performance.
ALTER TABLE public.ideas
    ADD COLUMN IF NOT EXISTS pitch_deck text,
    ADD COLUMN IF NOT EXISTS product_requirements_document text,
    ADD COLUMN IF NOT EXISTS provisional_patent text;
