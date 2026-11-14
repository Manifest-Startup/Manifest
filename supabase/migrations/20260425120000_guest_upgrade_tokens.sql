-- One-time tokens for guests to claim a full account via email link (voice / hands-free onboarding).

CREATE TABLE IF NOT EXISTS public.guest_upgrade_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users (user_id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ NULL,
    CONSTRAINT guest_upgrade_tokens_email_lower CHECK (email = lower(email))
);

CREATE INDEX IF NOT EXISTS idx_guest_upgrade_tokens_hash ON public.guest_upgrade_tokens (token_hash)
    WHERE used_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_guest_upgrade_tokens_user ON public.guest_upgrade_tokens (user_id);

COMMENT ON TABLE public.guest_upgrade_tokens IS 'Email verification tokens for upgrading guest users to full accounts without merge flow.';
