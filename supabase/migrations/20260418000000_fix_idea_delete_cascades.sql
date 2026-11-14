-- Migration: allow deleting ideas with generated artifacts and comments
-- Created: April 18, 2026

ALTER TABLE IF EXISTS "public"."comments"
    DROP CONSTRAINT IF EXISTS "comments_idea_id_fkey";

ALTER TABLE IF EXISTS "public"."comments"
    ADD CONSTRAINT "comments_idea_id_fkey"
    FOREIGN KEY ("idea_id")
    REFERENCES "public"."ideas"("idea_id")
    ON DELETE CASCADE;

ALTER TABLE IF EXISTS "public"."comments"
    DROP CONSTRAINT IF EXISTS "comments_pitch_id_fkey";

ALTER TABLE IF EXISTS "public"."comments"
    ADD CONSTRAINT "comments_pitch_id_fkey"
    FOREIGN KEY ("pitch_id")
    REFERENCES "public"."pitch_decks"("pitch_id")
    ON DELETE CASCADE;

ALTER TABLE IF EXISTS "public"."pitch_decks"
    DROP CONSTRAINT IF EXISTS "pitch_decks_idea_id_fkey";

ALTER TABLE IF EXISTS "public"."pitch_decks"
    ADD CONSTRAINT "pitch_decks_idea_id_fkey"
    FOREIGN KEY ("idea_id")
    REFERENCES "public"."ideas"("idea_id")
    ON UPDATE CASCADE
    ON DELETE CASCADE;

ALTER TABLE IF EXISTS "public"."product_requirements_documents"
    DROP CONSTRAINT IF EXISTS "product_requirements_documents_idea_id_fkey";

ALTER TABLE IF EXISTS "public"."product_requirements_documents"
    ADD CONSTRAINT "product_requirements_documents_idea_id_fkey"
    FOREIGN KEY ("idea_id")
    REFERENCES "public"."ideas"("idea_id")
    ON DELETE CASCADE;

ALTER TABLE IF EXISTS "public"."intellectual_properties"
    DROP CONSTRAINT IF EXISTS "intellectual_properties_idea_id_fkey";

ALTER TABLE IF EXISTS "public"."intellectual_properties"
    ADD CONSTRAINT "intellectual_properties_idea_id_fkey"
    FOREIGN KEY ("idea_id")
    REFERENCES "public"."ideas"("idea_id")
    ON DELETE CASCADE;
