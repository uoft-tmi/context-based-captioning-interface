CREATE EXTENSION IF NOT EXISTS pg_cron;

SELECT cron.schedule(
    'expire-sessions',
    '*/5 * * * *',
    $$
        UPDATE sessions 
        SET status = 'finalized', updated_at = NOW()
        WHERE status = 'active'
        AND expires_at < NOW();
    $$
);