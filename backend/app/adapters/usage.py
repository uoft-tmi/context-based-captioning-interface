"""Conservative provider budgets shared across replicas and process restarts."""
from uuid import UUID

from asyncpg import Pool

from app.core.config import Settings
from app.core.exceptions import ProviderRequestError


class PostgresTranscriptionBudget:
    def __init__(self, db: Pool, settings: Settings):
        self._db, self._settings = db, settings

    async def reserve(self, session_id: UUID, action: str, audio_ms: int = 0) -> None:
        settings = self._settings
        if not settings.TRANSCRIPTION_ENABLED:
            raise ProviderRequestError("Transcription is temporarily disabled by the administrator.")
        try:
            async with self._db.acquire(timeout=settings.DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
                async with conn.transaction():
                    # Serialize check + insert across every worker/provider using this DB.
                    await conn.execute("SELECT pg_advisory_xact_lock(824624112)")
                    user_id = await conn.fetchval("""SELECT user_id FROM sessions WHERE id=$1
                        AND stream_id IS NOT NULL AND stream_lease_expires_at > clock_timestamp()
                        AND deleting_at IS NULL""", session_id)
                    if user_id is None:
                        raise ProviderRequestError("The recording is no longer available.")
                    usage = await conn.fetchrow("""SELECT
                        COUNT(*) FILTER (WHERE reserved_at > clock_timestamp()-INTERVAL '60 seconds') AS minute_calls,
                        COUNT(*) FILTER (WHERE reserved_at >= date_trunc('day', clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC') AS day_calls,
                        COUNT(*) FILTER (WHERE user_id=$1 AND reserved_at >= date_trunc('day', clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC') AS user_calls,
                        COALESCE(SUM(audio_ms) FILTER (WHERE reserved_at >= date_trunc('day', clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'),0) AS day_audio,
                        COALESCE(SUM(audio_ms) FILTER (WHERE user_id=$1 AND reserved_at >= date_trunc('day', clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'),0) AS user_audio,
                        MAX(reserved_at) FILTER (WHERE action='transcribe') AS last_chunk
                        FROM provider_usage
                        WHERE reserved_at >= LEAST(date_trunc('day', clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC', clock_timestamp()-INTERVAL '60 seconds')""", user_id)
                    if usage['minute_calls'] >= settings.PROVIDER_REQUESTS_PER_MINUTE:
                        raise ProviderRequestError("The demo request limit was reached. Please wait a minute before recording again.")
                    if usage['day_calls'] >= settings.PROVIDER_REQUESTS_PER_DAY or usage['user_calls'] >= settings.PROVIDER_REQUESTS_PER_USER_PER_DAY:
                        raise ProviderRequestError("The daily demo request allowance is used up. It resets at midnight UTC.")
                    # Groq bills short files as at least ten seconds. Reserve that floor
                    # for every provider as a conservative audio allowance.
                    billed_ms = max(audio_ms, 10000) if action == 'transcribe' else 0
                    if usage['day_audio'] + billed_ms > settings.PROVIDER_AUDIO_SECONDS_PER_DAY * 1000 or usage['user_audio'] + billed_ms > settings.PROVIDER_AUDIO_SECONDS_PER_USER_PER_DAY * 1000:
                        raise ProviderRequestError("The daily demo audio allowance is used up. It resets at midnight UTC.")
                    if action == 'transcribe' and usage['last_chunk'] is not None:
                        elapsed_ms = await conn.fetchval("SELECT EXTRACT(EPOCH FROM (clock_timestamp()-$1::timestamptz))*1000", usage['last_chunk'])
                        if elapsed_ms < settings.PROVIDER_MIN_CHUNK_INTERVAL_MS:
                            raise ProviderRequestError("Audio arrived too quickly. Please restart recording and speak normally.")
                    await conn.execute("INSERT INTO provider_usage(user_id,session_id,action,audio_ms) VALUES($1,$2,$3,$4)", user_id, session_id, action, billed_ms)
        except ProviderRequestError:
            raise
        except Exception as exc:
            # No database/migration means no inference, rather than unlimited spend.
            raise ProviderRequestError("Transcription usage checks are unavailable. Please contact the administrator.") from exc
