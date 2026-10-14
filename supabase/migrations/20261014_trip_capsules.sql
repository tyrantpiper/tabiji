-- Migration: Trip Time Capsule (Sealed Blind Journal & Unveiling Ceremony)
-- Date: 2026-10-14

-- 1. Create trip_capsule_entries table
CREATE TABLE IF NOT EXISTS public.trip_capsule_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL REFERENCES public.itineraries(id) ON DELETE CASCADE,
    day_number INT NOT NULL, -- 0 for overall trip finale, 1..N for day capsule
    author_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    mood_emoji VARCHAR(16) NOT NULL DEFAULT '✨',
    content TEXT NOT NULL,
    photo_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_trip_day_author UNIQUE(trip_id, day_number, author_id)
);

-- 2. Add destination end time & unlocked flag to itineraries table
ALTER TABLE public.itineraries
ADD COLUMN IF NOT EXISTS end_date_utc TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS is_capsule_unlocked BOOLEAN NOT NULL DEFAULT false;

-- 3. Composite indexes for high-speed lookup
CREATE INDEX IF NOT EXISTS idx_capsule_trip_day 
ON public.trip_capsule_entries(trip_id, day_number);

CREATE INDEX IF NOT EXISTS idx_capsule_trip_author 
ON public.trip_capsule_entries(trip_id, author_id);

-- 4. Enable Row Level Security (RLS)
ALTER TABLE public.trip_capsule_entries ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    DROP POLICY IF EXISTS "Capsule read security isolation" ON public.trip_capsule_entries;
    DROP POLICY IF EXISTS "Capsule author insert policy" ON public.trip_capsule_entries;
    DROP POLICY IF EXISTS "Capsule author update policy" ON public.trip_capsule_entries;
END $$;

-- 5. RLS Policy: SELECT isolation
-- Authors can always read their own entries.
-- Collaborators can only read entries when trip is unlocked AND destination end_date_utc is reached.
CREATE POLICY "Capsule read security isolation"
ON public.trip_capsule_entries
FOR SELECT USING (
    auth.uid() = author_id
    OR (
        EXISTS (
            SELECT 1 FROM public.itineraries t
            LEFT JOIN public.trip_members tm ON tm.itinerary_id = t.id
            WHERE t.id = trip_capsule_entries.trip_id
              AND (t.user_id = auth.uid() OR t.created_by = auth.uid()::text OR tm.user_id = auth.uid()::text)
              AND t.is_capsule_unlocked = true
              AND CURRENT_TIMESTAMP >= t.end_date_utc
        )
    )
);

-- 6. RLS Policy: INSERT mutation
-- Authors can insert their own entries, but once unlocked, mutations are frozen.
CREATE POLICY "Capsule author insert policy"
ON public.trip_capsule_entries
FOR INSERT WITH CHECK (
    auth.uid() = author_id
    AND NOT EXISTS (
        SELECT 1 FROM public.itineraries
        WHERE id = trip_capsule_entries.trip_id
          AND (is_capsule_unlocked = true OR CURRENT_TIMESTAMP >= end_date_utc)
    )
);

-- 7. RLS Policy: UPDATE mutation
CREATE POLICY "Capsule author update policy"
ON public.trip_capsule_entries
FOR UPDATE USING (
    auth.uid() = author_id
    AND NOT EXISTS (
        SELECT 1 FROM public.itineraries
        WHERE id = trip_capsule_entries.trip_id
          AND (is_capsule_unlocked = true OR CURRENT_TIMESTAMP >= end_date_utc)
    )
);

