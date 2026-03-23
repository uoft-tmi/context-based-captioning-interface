CREATE EXTENSION IF NOT EXISTS pg_cron;

SELECT cron.schedule(
    'expire-sessions',
    '*/5 * * * *',
    $$
        UPDATE sessions 
        SET  is_active = false, finalized_at = NOW(), error = 'Session expired'
        WHERE is_active = true
        AND expires_at < NOW();
    $$
);