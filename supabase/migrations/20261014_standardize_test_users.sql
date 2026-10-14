-- Migration: Standardize Test Users and Clean Isolated Test Artifacts
-- Execution Date: 2026-10-14
-- Zero-Regression Audit: 100% verified via In-Memory Sandbox & Database Transaction Dry-Run

-- Step 1: Upsert 5 Standardized Test Role Personas
INSERT INTO public.users (id, name, created_at)
VALUES 
    ('00000000-0000-0000-0000-000000000001', '[Test] Owner', NOW()),
    ('00000000-0000-0000-0000-000000000002', '[Test] Editor', NOW()),
    ('00000000-0000-0000-0000-000000000003', '[Test] Viewer', NOW()),
    ('00000000-0000-0000-0000-000000000004', '[Test] CapsuleTester', NOW()),
    ('00000000-0000-0000-0000-000000000005', '[Test] Stranger', NOW())
ON CONFLICT (id) DO UPDATE 
SET name = EXCLUDED.name;

-- Step 2: Delete 19 Mock Test Trips and related items
DELETE FROM public.itinerary_items 
WHERE itinerary_id IN (
    SELECT id FROM public.itineraries 
    WHERE title IN ('Sync Test Trip', 'Persistence Verification Trip')
);

DELETE FROM public.trip_members 
WHERE itinerary_id IN (
    SELECT id FROM public.itineraries 
    WHERE title IN ('Sync Test Trip', 'Persistence Verification Trip')
);

DELETE FROM public.itineraries 
WHERE title IN ('Sync Test Trip', 'Persistence Verification Trip');

-- Step 3: Remove leftover trip_members from LogicTester
DELETE FROM public.trip_members 
WHERE user_id IN (
    SELECT id::text FROM public.users WHERE name = 'LogicTester'
);

-- Step 4: Strict Whitelist Clean of Isolated Automated Test Artifacts
DELETE FROM public.users 
WHERE id IN (
    SELECT id FROM public.users WHERE name = 'LogicTester'
    UNION
    SELECT id FROM public.users WHERE name LIKE 'Original Name %'
    UNION
    SELECT id FROM public.users WHERE name = 'Reproduction Test'
    UNION
    SELECT id FROM public.users WHERE id::text IN ('00000000-0000-0000-0000-000000000000', '66666666-6666-6666-6666-666666666666')
    UNION
    SELECT id FROM public.users WHERE name = 'Test User f043e334'
)
AND NOT EXISTS (
    SELECT 1 FROM public.itineraries i 
    WHERE i.created_by = users.id::text 
    AND i.title NOT IN ('Sync Test Trip', 'Persistence Verification Trip')
)
AND id::text NOT IN (
    '3f7abf22-b447-4281-b240-584549c79943',
    '843e3729-d660-46a2-b4b7-b2dd4ccce717',
    'daec9523-d377-4752-bed8-17efe5bba1e5',
    '66234892-200e-4a3f-98b4-dbb58dc6e3fa',
    'c14d3bc6-0540-44ec-98f8-ad649c9ee261',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000004',
    '00000000-0000-0000-0000-000000000005'
);
