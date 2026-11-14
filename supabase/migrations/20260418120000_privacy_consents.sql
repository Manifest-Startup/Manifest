-- First-party privacy consent audit trail for GDPR/CPRA-style analytics and outreach choices.

CREATE TABLE IF NOT EXISTS public.privacy_consents (
    consent_id uuid DEFAULT gen_random_uuid() NOT NULL,
    consent_updated_at timestamp with time zone DEFAULT now() NOT NULL,
    user_id text,
    visitor_id text,
    source text NOT NULL DEFAULT 'settings',
    policy_version text NOT NULL,
    analytics_enabled boolean NOT NULL DEFAULT false,
    communications_enabled boolean NOT NULL DEFAULT false,
    do_not_sell_or_share boolean NOT NULL DEFAULT false,
    consent_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    ip_hash text,
    CONSTRAINT privacy_consents_pkey PRIMARY KEY (consent_id)
);

COMMENT ON TABLE public.privacy_consents IS 'Audit trail of privacy choices for optional analytics, communications, and CPRA-style sharing opt-outs.';
COMMENT ON COLUMN public.privacy_consents.user_id IS 'Authenticated user tied to the choice, when available.';
COMMENT ON COLUMN public.privacy_consents.visitor_id IS 'Anonymous browser-scoped identifier used only to persist privacy choices.';
COMMENT ON COLUMN public.privacy_consents.consent_payload IS 'Canonical JSON payload for the recorded privacy choice at save time.';
COMMENT ON COLUMN public.privacy_consents.ip_hash IS 'Salted one-way hash of the request IP, kept for compliance auditing without storing raw IP.';

CREATE INDEX IF NOT EXISTS idx_privacy_consents_user_updated
    ON public.privacy_consents USING btree (user_id, consent_updated_at DESC)
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_privacy_consents_visitor_updated
    ON public.privacy_consents USING btree (visitor_id, consent_updated_at DESC)
    WHERE visitor_id IS NOT NULL;

ALTER TABLE public.privacy_consents ENABLE ROW LEVEL SECURITY;

GRANT ALL ON TABLE public.privacy_consents TO anon;
GRANT ALL ON TABLE public.privacy_consents TO authenticated;
GRANT ALL ON TABLE public.privacy_consents TO service_role;
