-- Migration: Dual-Track Authentication Credentials & Silent Upgrade Support
-- Execution Date: 2026-10-23
-- Purpose: Decouples immutable identity anchor (id: UUID) from revocable recovery credentials (recovery_key_id, recovery_secret_hash).

ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS recovery_key_id TEXT,
ADD COLUMN IF NOT EXISTS recovery_secret_hash TEXT,
ADD COLUMN IF NOT EXISTS recovery_key_encrypted TEXT,
ADD COLUMN IF NOT EXISTS credential_version INT DEFAULT 1 NOT NULL,
ADD COLUMN IF NOT EXISTS recovery_updated_at TIMESTAMPTZ DEFAULT NOW();

-- O(1) B-tree lookup index for Stripe-style prefixed recovery key lookup
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_recovery_key_id 
ON public.users(recovery_key_id) 
WHERE recovery_key_id IS NOT NULL;

-- 🛡️ 收攏 PostgREST Data API 欄位權限：防止匿名傾印敏感認證欄位
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'users') THEN
        REVOKE SELECT ON public.users FROM anon;
        GRANT SELECT (id, name, created_at) ON public.users TO anon;
    END IF;
END $$;
