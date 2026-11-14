-- Version history: distinguish manual / auto / system snapshots and store content hash for dedup.

ALTER TABLE public.idea_versions
  ADD COLUMN IF NOT EXISTS version_kind text NOT NULL DEFAULT 'manual',
  ADD COLUMN IF NOT EXISTS content_hash text;

COMMENT ON COLUMN public.idea_versions.version_kind IS 'manual | auto | system';
COMMENT ON COLUMN public.idea_versions.content_hash IS 'SHA256 of canonical snapshot JSON for deduplication';

UPDATE public.idea_versions
SET version_kind = 'auto'
WHERE change_summary = 'Auto-saved';

UPDATE public.idea_versions
SET version_kind = 'system'
WHERE change_summary = 'Auto-saved before restore'
   OR change_summary ILIKE 'restored to version%';

ALTER TABLE public.idea_versions
  DROP CONSTRAINT IF EXISTS idea_versions_version_kind_check;

ALTER TABLE public.idea_versions
  ADD CONSTRAINT idea_versions_version_kind_check
  CHECK (version_kind IN ('manual', 'auto', 'system'));

CREATE INDEX IF NOT EXISTS idx_idea_versions_idea_kind_created
  ON public.idea_versions (idea_id, version_kind, created_at);
