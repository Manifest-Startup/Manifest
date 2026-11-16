-- Pitch reel likes, saves, comments and share events move to Open Media
-- (saves are dropped: Open Media has no save concept and Manifest never listed them).
-- Refuses to run if any table holds rows other than the three demo fixtures seeded
-- by 20260326000000_add_pitch_reels_social.sql.

DO $$
DECLARE
    demo_reels uuid[] := ARRAY[
        '00000000-0000-0000-0000-00000000b201',
        '00000000-0000-0000-0000-00000000b202',
        '00000000-0000-0000-0000-00000000b203'
    ]::uuid[];
    t text;
    has_rows boolean;
BEGIN
    FOREACH t IN ARRAY ARRAY['pitch_reel_likes', 'pitch_reel_saves', 'pitch_reel_comments', 'pitch_reel_share_events'] LOOP
        IF to_regclass('public.' || t) IS NOT NULL THEN
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM public.%I WHERE reel_id <> ALL ($1))', t)
                INTO has_rows USING demo_reels;
            IF has_rows THEN
                RAISE EXCEPTION 'public.% holds real rows; refusing to drop pitch reel social tables', t;
            END IF;
        END IF;
    END LOOP;
END $$;

DROP TABLE IF EXISTS public.pitch_reel_comments;
DROP TABLE IF EXISTS public.pitch_reel_likes;
DROP TABLE IF EXISTS public.pitch_reel_saves;
DROP TABLE IF EXISTS public.pitch_reel_share_events;
