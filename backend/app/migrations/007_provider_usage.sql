-- Keep usage independent of sessions so deleting a transcript never resets quotas.
CREATE TABLE IF NOT EXISTS public.provider_usage (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL,
    session_id UUID NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('start', 'notes', 'transcribe', 'finalize')),
    audio_ms INTEGER NOT NULL DEFAULT 0 CHECK (audio_ms >= 0),
    reserved_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS provider_usage_time ON public.provider_usage (reserved_at);
CREATE INDEX IF NOT EXISTS provider_usage_user_time ON public.provider_usage (user_id, reserved_at);
ALTER TABLE public.provider_usage ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.provider_usage FROM PUBLIC;
DO $migration$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.provider_usage FROM anon;
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON public.provider_usage FROM authenticated;
    END IF;
END;
$migration$;
