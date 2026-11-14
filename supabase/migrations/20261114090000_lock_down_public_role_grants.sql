-- The application accesses relational data through its private DATABASE_URL
-- connection and uses the Supabase service-role key only for Storage. The web
-- client does not use supabase-js for table/RPC access. Do not grant the
-- PostgREST anon/authenticated roles blanket access to public objects.
--
-- Revoke access on objects that already exist, and fix defaults for objects
-- created by the postgres role that owns every application table. PostgreSQL
-- owners (postgres and supabase_admin) retain their normal owner privileges.
-- The service-role key is used only for Storage, so API roles need no access
-- to objects in the public schema.

REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM anon, authenticated, service_role;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated, service_role;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC, anon, authenticated, service_role;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL ON TABLES FROM anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated, service_role;

-- Objects owned by supabase_admin are managed by Supabase; changing that
-- role's default privileges requires platform superuser rights, so only the
-- postgres role (which owns every application table) is covered here.

-- Trigger functions are invoked by their triggers; they do not need to be
-- callable as PostgREST RPCs. Lock search_path to prevent object shadowing.
ALTER FUNCTION public.handle_new_user() SET search_path = public, pg_temp;
ALTER FUNCTION public.update_conversation_on_message() SET search_path = public, pg_temp;
REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated, service_role;

-- This trigger function is SECURITY INVOKER, so message insertion continues
-- to execute its conversation-update trigger under the inserting role's
-- existing table policies. It is not an RPC surface.
REVOKE ALL ON FUNCTION public.update_conversation_on_message() FROM PUBLIC, anon, authenticated, service_role;
