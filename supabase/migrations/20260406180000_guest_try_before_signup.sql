-- Ephemeral "try without an account" users: server-backed guest rows + merge into a full account after signup.
-- Retention: guest_expires_at is set at creation (e.g. 30 days). Stale guests may be purged by a scheduled job (see docs/API.md).

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_guest BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS guest_merge_secret TEXT NULL;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS guest_created_at TIMESTAMPTZ NULL;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS guest_expires_at TIMESTAMPTZ NULL;

COMMENT ON COLUMN public.users.is_guest IS 'True for try-before-signup identities; workspace can be merged into a registered account.';
COMMENT ON COLUMN public.users.guest_merge_secret IS 'Single-use plaintext secret shown once at guest creation; cleared after successful merge.';
COMMENT ON COLUMN public.users.guest_created_at IS 'When the guest session row was created.';
COMMENT ON COLUMN public.users.guest_expires_at IS 'Optional TTL for cleanup and merge validation.';

CREATE INDEX IF NOT EXISTS idx_users_is_guest ON public.users (is_guest) WHERE is_guest = TRUE;
