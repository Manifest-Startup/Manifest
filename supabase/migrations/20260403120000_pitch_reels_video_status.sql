-- Pitch reel video generation lifecycle and one reel per published idea

ALTER TABLE "public"."pitch_reels"
    ADD COLUMN IF NOT EXISTS "video_status" text NOT NULL DEFAULT 'ready';

ALTER TABLE "public"."pitch_reels"
    ADD COLUMN IF NOT EXISTS "video_generation_error" text;

COMMENT ON COLUMN "public"."pitch_reels"."video_status" IS 'ready | pending | processing | failed — user-generated reels use pending until Gemini completes.';

CREATE UNIQUE INDEX IF NOT EXISTS "pitch_reels_idea_id_unique"
    ON "public"."pitch_reels" ("idea_id")
    WHERE "idea_id" IS NOT NULL;
