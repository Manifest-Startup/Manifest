-- Pitch Shorts move to Open Media (docs/OPEN_MEDIA_INTEGRATION_PLAN.md, docs/adr/0001).
-- The video file, likes, comments and reshares now live in Open Media; a reel keeps
-- only a pointer to its Open Media clip post.
--
-- - om_post_id: the Open Media post id for the reel's clip (NULL until posted).
-- - video_generated_at: last successful Veo generation (cost guard: at most one per
--   idea per 30 days, see app/services/pitch_reels/video_worker.py).
-- - video_status gains 'needs_open_media' (free text column; no constraint change).
-- - video_data (BYTEA video bytes, added by old startup DDL) is dropped. The guard
--   refuses to run if any reel still holds bytes, so nothing is lost silently.

ALTER TABLE public.pitch_reels ADD COLUMN IF NOT EXISTS om_post_id TEXT;
ALTER TABLE public.pitch_reels ADD COLUMN IF NOT EXISTS video_generated_at TIMESTAMP WITH TIME ZONE;
CREATE UNIQUE INDEX IF NOT EXISTS idx_pitch_reels_om_post_id
    ON public.pitch_reels (om_post_id) WHERE om_post_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pitch_reels_creator_status
    ON public.pitch_reels (creator_user_id, video_status);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'pitch_reels' AND column_name = 'video_data'
    ) THEN
        IF EXISTS (SELECT 1 FROM public.pitch_reels WHERE video_data IS NOT NULL) THEN
            RAISE EXCEPTION 'pitch_reels.video_data still holds video bytes; export or clear them before dropping the column';
        END IF;
        ALTER TABLE public.pitch_reels DROP COLUMN video_data;
    END IF;
END $$;
