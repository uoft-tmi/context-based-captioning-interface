-- Apply after 001-005. Retains all existing session and transcript records.
CREATE TABLE IF NOT EXISTS public.account_plans (
    user_id UUID PRIMARY KEY,
    plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'paid'))
);
ALTER TABLE public.account_plans ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.account_plans FROM PUBLIC;
-- Only administrators/backend credentials can change paid status.
DO $migration$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.account_plans FROM anon;
        REVOKE INSERT, UPDATE, DELETE ON public.sessions, public.session_notes FROM anon;
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON public.account_plans FROM authenticated;
        REVOKE INSERT, UPDATE, DELETE ON public.sessions, public.session_notes FROM authenticated;
    END IF;
END;
$migration$;

ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS name TEXT;
UPDATE public.sessions SET name = 'Session ' || id::text WHERE name IS NULL;
ALTER TABLE public.sessions ALTER COLUMN name SET NOT NULL;
ALTER TABLE public.sessions ALTER COLUMN name SET DEFAULT ('Session ' || gen_random_uuid()::text);
CREATE UNIQUE INDEX IF NOT EXISTS sessions_unique_name_per_user ON public.sessions (user_id, lower(btrim(regexp_replace(name, '\s+', ' ', 'g'))));
ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS transcript_text TEXT;
ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS recording_limit_seconds INTEGER NOT NULL DEFAULT 30;
ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS recorded_duration_ms INTEGER NOT NULL DEFAULT 0 CHECK (recorded_duration_ms >= 0);
ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS recording_started_at TIMESTAMPTZ;
ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS deleting_at TIMESTAMPTZ;
-- Expiry only ends a session; records/files are removed only by explicit deletion.
