-- Optional maintenance. Correctness does not depend on pg_cron being installed.
-- Enable pg_cron on Supabase first, then rerun this file to schedule cleanup.
DO $migration$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.schedule(
            'expire-sessions', '*/5 * * * *',
            $job$UPDATE public.sessions
                 SET is_active = FALSE, finalized_at = clock_timestamp(),
                     error = COALESCE(error, 'Session expired')
                 WHERE is_active = TRUE AND expires_at <= NOW();$job$
        );
    END IF;
END;
$migration$;
