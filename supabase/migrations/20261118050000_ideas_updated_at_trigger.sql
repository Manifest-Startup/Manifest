-- Keep ideas.updated_at current on every change (title, description, documents, publishing).
-- Nothing in the backend set it, so the vault export's incremental sync (ADR 0005) could not
-- tell which ideas changed. Additive: one function and one trigger; existing NULLs are backfilled
-- from created_at. ideas.updated_at is `timestamp without time zone`, so it stores UTC.

CREATE OR REPLACE FUNCTION public.touch_ideas_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    NEW.updated_at := timezone('utc', now());
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.touch_ideas_updated_at() FROM PUBLIC, anon, authenticated, service_role;

DROP TRIGGER IF EXISTS ideas_touch_updated_at ON public.ideas;
CREATE TRIGGER ideas_touch_updated_at
    BEFORE UPDATE ON public.ideas
    FOR EACH ROW EXECUTE FUNCTION public.touch_ideas_updated_at();

UPDATE public.ideas SET updated_at = timezone('utc', created_at) WHERE updated_at IS NULL;
