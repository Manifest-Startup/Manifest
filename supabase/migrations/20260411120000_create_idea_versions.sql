-- Create the idea snapshot table before adding version-kind/hash metadata.
-- This mirrors the production Replit PostgreSQL schema inspected during the
-- Replit -> Supabase migration on 2026-11-13.

CREATE TABLE IF NOT EXISTS public.idea_versions (
    version_id uuid DEFAULT gen_random_uuid() NOT NULL,
    idea_id uuid NOT NULL,
    version_number integer NOT NULL,
    title varchar(500),
    description text,
    business_model_canvas text,
    pitch_deck text,
    product_requirements_document text,
    provisional_patent text,
    created_by uuid NOT NULL,
    created_at timestamptz DEFAULT now(),
    change_summary varchar(500),
    CONSTRAINT idea_versions_pkey PRIMARY KEY (version_id),
    CONSTRAINT idea_versions_idea_id_version_number_key UNIQUE (idea_id, version_number),
    CONSTRAINT idea_versions_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES public.users (user_id),
    CONSTRAINT idea_versions_idea_id_fkey
        FOREIGN KEY (idea_id) REFERENCES public.ideas (idea_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_idea_versions_created
    ON public.idea_versions USING btree (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_idea_versions_idea
    ON public.idea_versions USING btree (idea_id);

ALTER TABLE public.idea_versions DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.idea_versions NO FORCE ROW LEVEL SECURITY;
