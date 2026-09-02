-- =========================================================
-- Meow Ware License & Access Key Database Schema (Supabase)
-- =========================================================

-- 1. Table for Access Keys
CREATE TABLE IF NOT EXISTS public.access_keys (
    id BIGSERIAL PRIMARY KEY,
    key_code VARCHAR(64) UNIQUE NOT NULL,
    key_type VARCHAR(20) NOT NULL DEFAULT 'daily', -- 'daily', 'lifetime', 'custom'
    created_by VARCHAR(64) NOT NULL,
    claimed_by VARCHAR(64),
    claimed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    duration_hours INT DEFAULT 12,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Table for Discord User Cooldowns (12-hour timer)
CREATE TABLE IF NOT EXISTS public.user_cooldowns (
    discord_id VARCHAR(64) PRIMARY KEY,
    last_generated TIMESTAMPTZ DEFAULT NOW(),
    last_key_code VARCHAR(64)
);

-- 3. Indexes for fast lookup
CREATE INDEX IF NOT EXISTS idx_access_keys_key_code ON public.access_keys (key_code);
CREATE INDEX IF NOT EXISTS idx_access_keys_is_active ON public.access_keys (is_active);
CREATE INDEX IF NOT EXISTS idx_access_keys_claimed_by ON public.access_keys (claimed_by);

-- 4. Enable Row Level Security (RLS) & Policies
ALTER TABLE public.access_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_cooldowns ENABLE ROW LEVEL SECURITY;

-- Allow read access for key validation
CREATE POLICY "Allow public key validation" ON public.access_keys
    FOR SELECT USING (true);

-- Allow full access
CREATE POLICY "Allow full access to keys" ON public.access_keys
    FOR ALL USING (true);

CREATE POLICY "Allow full access to cooldowns" ON public.user_cooldowns
    FOR ALL USING (true);
