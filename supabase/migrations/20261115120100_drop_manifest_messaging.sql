-- Direct messages move to Open Media (fresh start: nothing is migrated).
-- Drops Manifest's own conversations, messages and the unused (fake) E2E key table.
-- Refuses to run if any of them still holds rows.

DO $$
BEGIN
    IF to_regclass('public.messages') IS NOT NULL AND EXISTS (SELECT 1 FROM public.messages) THEN
        RAISE EXCEPTION 'public.messages is not empty; refusing to drop Manifest messaging tables';
    END IF;
    IF to_regclass('public.conversations') IS NOT NULL AND EXISTS (SELECT 1 FROM public.conversations) THEN
        RAISE EXCEPTION 'public.conversations is not empty; refusing to drop Manifest messaging tables';
    END IF;
    IF to_regclass('public.user_encryption_keys') IS NOT NULL
        AND EXISTS (SELECT 1 FROM public.user_encryption_keys) THEN
        RAISE EXCEPTION 'public.user_encryption_keys is not empty; refusing to drop Manifest messaging tables';
    END IF;
END $$;

DROP TRIGGER IF EXISTS trigger_update_conversation_on_message ON public.messages;
DROP FUNCTION IF EXISTS public.update_conversation_on_message();
DROP TABLE IF EXISTS public.messages;
DROP TABLE IF EXISTS public.conversations;
DROP TABLE IF EXISTS public.user_encryption_keys;
