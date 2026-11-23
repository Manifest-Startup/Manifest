-- Standing authorizations (ADR 0021): the person lets Manifest take one kind of tier 2 action
-- (today only message.send) for named recipients without asking each time, within a weekly
-- cap and an expiry, until they revoke it. Each use is still recorded as an approval row
-- (decided_via = 'standing:<id>'). Additive: one table, one index. Backend-only (RLS on).

CREATE TABLE IF NOT EXISTS public.standing_authorizations (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    action        text NOT NULL CHECK (action IN ('message.send')),
    recipients    text[] NOT NULL CHECK (cardinality(recipients) BETWEEN 1 AND 20),
    max_per_week  integer NOT NULL CHECK (max_per_week BETWEEN 1 AND 20),
    note          text NOT NULL DEFAULT '' CHECK (char_length(note) <= 300),
    status        text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    expires_at    timestamptz NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    revoked_at    timestamptz
);
CREATE INDEX IF NOT EXISTS standing_authorizations_user_idx
    ON public.standing_authorizations (user_id, status);

ALTER TABLE public.standing_authorizations ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON public.standing_authorizations FROM anon, authenticated, service_role;
