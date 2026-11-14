-- Fix security issue: Set search_path for handle_new_user function
-- This prevents search_path injection attacks by explicitly setting the search path
-- Reference: https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable

CREATE OR REPLACE FUNCTION "public"."handle_new_user"() 
RETURNS "trigger"
LANGUAGE "plpgsql" 
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
begin
  insert into public.users (user_id, email, created_at, updated_at)
  values (new.id, new.email, now(), now());
  return new;
end;
$$;

