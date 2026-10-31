-- Apply the repaired 003 and 004 before this file on existing deployments too.
ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS stream_id UUID;
ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS stream_lease_expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS sessions_active_expiry_idx
ON public.sessions (expires_at) WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS sessions_user_history_idx
ON public.sessions (user_id, created_at DESC);
