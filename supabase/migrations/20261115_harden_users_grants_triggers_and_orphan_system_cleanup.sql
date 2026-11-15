-- Migration: 20261115_harden_users_grants_triggers_and_orphan_system_cleanup.sql
-- Purpose:
--   1. Revoke all direct Data API (PostgREST) privileges on public.users from anon and authenticated
--      to block legacy UUID enumeration & ATO while preserving full service_role access for FastAPI.
--   2. Harden public.users RLS policies so no permissive USING (true) SELECT policy remains.
--   3. Pin search_path = public on SECURITY DEFINER trigger functions (sync_user_profile_changes / populate_trip_member_info).
--   4. Clean up orphan SYSTEM-seeded itineraries that have 0 remaining trip_members (cascading to child items).

DO $$
DECLARE
    pol RECORD;
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'users') THEN
        ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

        REVOKE ALL ON TABLE public.users FROM anon;
        REVOKE ALL ON TABLE public.users FROM authenticated;
        GRANT ALL PRIVILEGES ON TABLE public.users TO service_role;

        -- Drop ALL existing policies (SELECT / INSERT / UPDATE / DELETE / ALL) on public.users
        FOR pol IN
            SELECT policyname
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = 'users'
        LOOP
            EXECUTE format('DROP POLICY IF EXISTS %I ON public.users;', pol.policyname);
        END LOOP;

        DROP POLICY IF EXISTS "Users can view own profile" ON public.users;
        CREATE POLICY "Users can view own profile" ON public.users
            FOR SELECT TO authenticated
            USING (auth.uid()::text = id::text);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = 'sync_user_profile_changes'
    ) THEN
        ALTER FUNCTION public.sync_user_profile_changes() SET search_path = public;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = 'populate_trip_member_info'
    ) THEN
        ALTER FUNCTION public.populate_trip_member_info() SET search_path = public;
    END IF;
END $$;

-- Remove orphan SYSTEM sample itineraries with zero remaining members (ON DELETE CASCADE cleans child rows)
DELETE FROM public.itineraries AS i
WHERE i.created_by = 'SYSTEM'
  AND NOT EXISTS (
      SELECT 1
      FROM public.trip_members AS tm
      WHERE tm.itinerary_id = i.id
  );
