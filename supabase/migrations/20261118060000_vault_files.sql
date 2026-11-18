-- Vault sync (ADR 0007): the person's own vault files, kept in their account so every computer
-- they sign in on has the same vault, like iCloud Drive or OneDrive. One row per file path;
-- `sha256` drives conflict detection and `deleted` is a tombstone so deletions reach other
-- computers. Additive: one table, one index. Only the backend reads it (RLS on, no grants).

CREATE TABLE IF NOT EXISTS public.vault_files (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    path        text NOT NULL CHECK (char_length(path) BETWEEN 1 AND 400),
    content     text NOT NULL DEFAULT '' CHECK (octet_length(content) <= 524288),
    sha256      text NOT NULL DEFAULT '',
    deleted     boolean NOT NULL DEFAULT false,
    device      text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT vault_files_user_path_key UNIQUE (user_id, path)
);

CREATE INDEX IF NOT EXISTS vault_files_user_updated_idx
    ON public.vault_files (user_id, updated_at);

ALTER TABLE public.vault_files ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON public.vault_files FROM anon, authenticated, service_role;
