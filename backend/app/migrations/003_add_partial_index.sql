-- Repair stale/duplicate rows before enforcing one active session per user.
UPDATE public.sessions
SET is_active = FALSE, finalized_at = clock_timestamp(), error = COALESCE(error, 'Session expired')
WHERE is_active = TRUE AND expires_at <= NOW();

WITH ranked AS (
    SELECT id, row_number() OVER (PARTITION BY user_id ORDER BY created_at DESC, id DESC) AS position
    FROM public.sessions WHERE is_active = TRUE
)
UPDATE public.sessions s
SET is_active = FALSE, finalized_at = clock_timestamp(), error = COALESCE(error, 'Superseded duplicate session')
FROM ranked r WHERE s.id = r.id AND r.position > 1;

CREATE UNIQUE INDEX IF NOT EXISTS one_active_session_per_user
ON public.sessions (user_id) WHERE is_active = TRUE;
