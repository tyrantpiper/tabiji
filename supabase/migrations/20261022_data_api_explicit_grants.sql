-- Migration: 20261022_data_api_explicit_grants.sql
-- Description: Hardening Data API grants for Supabase 2026-10-30 breaking change,
--              enforcing RLS on user_preferences, and securing public schema tables, views, and sequences.

-- 1. 確保 user_preferences RLS 政策相容 (auth.uid()::text = user_id::text)
ALTER TABLE IF EXISTS public.user_preferences ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    DROP POLICY IF EXISTS "Users can read own preferences" ON public.user_preferences;
    DROP POLICY IF EXISTS "Users can manage own preferences" ON public.user_preferences;
    DROP POLICY IF EXISTS "Users can view their own preferences" ON public.user_preferences;
    DROP POLICY IF EXISTS "Users can manage their own preferences" ON public.user_preferences;
END $$;

CREATE POLICY "Users can view their own preferences" ON public.user_preferences
    FOR SELECT USING (auth.uid()::text = user_id::text);

CREATE POLICY "Users can manage their own preferences" ON public.user_preferences
    FOR ALL USING (auth.uid()::text = user_id::text);

-- 2. 針對現有核心業務資料表進行顯式 GRANT (PostgREST DAC 前置檢查)
DO $$
DECLARE
    tbl text;
    tables text[] := ARRAY[
        'app_settings',
        'expenses',
        'itineraries',
        'itinerary_items',
        'medicines',
        'notifications',
        'profiles',
        'push_subscriptions',
        'trip_capsule_entries',
        'trip_members',
        'user_preferences',
        'users'
    ];
BEGIN
    FOREACH tbl IN ARRAY tables LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = tbl) THEN
            EXECUTE format('GRANT SELECT ON TABLE public.%I TO anon;', tbl);
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO authenticated;', tbl);
            EXECUTE format('GRANT ALL PRIVILEGES ON TABLE public.%I TO service_role;', tbl);
        END IF;
    END LOOP;
END $$;

-- 3. 針對業務 View 進行顯式授權
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.views WHERE table_schema = 'public' AND table_name = 'user_trips_view') THEN
        GRANT SELECT ON public.user_trips_view TO anon, authenticated, service_role;
    END IF;
END $$;

-- 4. 針對 Sequence 授予存取權限 (保障自增 ID 寫入正常)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated, service_role;
