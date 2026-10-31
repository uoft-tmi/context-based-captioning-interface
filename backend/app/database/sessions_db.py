from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from app.core.config import get_settings
from asyncpg import Pool
from app.models.session import AccountOverview, Session, SessionMode


# ----------------- Helper Functions -----------------
def _row_to_session(row) -> Session:
    return Session(
        is_recording=row["stream_id"] is not None and row["stream_lease_expires_at"] is not None and row["stream_lease_expires_at"] > datetime.now(timezone.utc),
        name=row["name"],
        recording_limit_seconds=row["recording_limit_seconds"],
        recorded_duration_ms=row["recorded_duration_ms"],
        recording_started_at=row["recording_started_at"],
        deleting_at=row["deleting_at"],
        transcript_text=row.get("transcript_text"),
        has_transcript=row.get("has_transcript", row.get("transcript_text") is not None or row["transcript_key"] is not None),
        id=row["id"],
        user_id=row["user_id"],
        mode=SessionMode(row["mode"]),
        is_active=row["is_active"],
        error=row["error"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        finalized_at=row["finalized_at"],
        transcript_key=row["transcript_key"],
    )


# ----------------- Session Management -----------------
async def _expire_abandoned(conn, user_id: UUID) -> None:
    await conn.execute(
        """UPDATE sessions SET is_active = FALSE, finalized_at = clock_timestamp(),
           error = COALESCE(error, 'Session expired or stream worker lost')
           WHERE user_id = $1 AND is_active = TRUE
             AND (expires_at <= NOW() OR (stream_id IS NOT NULL AND stream_lease_expires_at <= NOW()))""",
        user_id,
    )


async def create_session(
    db: Pool,
    user_id: UUID,
    mode: str,
    name: str | None = None,
) -> Session:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        current_time = datetime.now(timezone.utc)
        async with conn.transaction():
            # Expire abandoned rows before the partial unique index checks the insert.
            # Never deactivate a healthy stream just because another tab creates a session.
            await _expire_abandoned(conn, user_id)
            plan = await _account(conn, user_id)
            row = await conn.fetchrow(
                """
                INSERT INTO sessions (user_id, mode, created_at, expires_at, name, recording_limit_seconds)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING *
                """,
                user_id,
                mode,
                current_time,
                current_time + timedelta(days=1),
                name or f"Session {uuid4().hex}",
                plan.recording_limit_seconds,
            )

    return _row_to_session(row)


async def get_active_session(db: Pool, user_id: UUID) -> Optional[Session]:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        await _expire_abandoned(conn, user_id)
        row = await conn.fetchrow(
            """
            SELECT * FROM sessions
            WHERE user_id = $1 AND is_active = TRUE
            AND expires_at > NOW()
            ORDER BY created_at DESC
            LIMIT 1
            """,
            user_id,
        )

    return _row_to_session(row) if row else None


async def get_session(
    db: Pool,
    session_id: UUID,
    user_id: UUID,
) -> Optional[Session]:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        await _expire_abandoned(conn, user_id)
        row = await conn.fetchrow(
            """
            SELECT * FROM sessions
            WHERE id = $1 AND user_id = $2
            """,
            session_id,
            user_id,
        )

    return _row_to_session(row) if row else None


async def get_all_sessions(db: Pool, user_id: UUID) -> list[Session]:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        await _expire_abandoned(conn, user_id)
        rows = await conn.fetch(
            """
            SELECT id,user_id,name,mode,is_active,error,created_at,expires_at,finalized_at,
                   transcript_key,recording_limit_seconds,recorded_duration_ms,recording_started_at,
                   stream_id,stream_lease_expires_at,deleting_at,
                   (transcript_text IS NOT NULL OR transcript_key IS NOT NULL) AS has_transcript
            FROM sessions
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )
    return [_row_to_session(row) for row in rows]


async def end_session(db: Pool, session_id: UUID, user_id: UUID) -> bool:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        row = await conn.fetchrow(
            """
            UPDATE sessions
            SET is_active = FALSE, finalized_at = COALESCE(finalized_at, clock_timestamp())
            WHERE id = $1 AND user_id = $2
              AND (stream_id IS NULL OR stream_lease_expires_at <= NOW())
            RETURNING id
            """,
            session_id,
            user_id,
        )
    return row is not None


async def mark_session_error(
    db: Pool,
    session_id: UUID,
    user_id: UUID,
    error: str,
) -> None:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET error = $3,
                is_active = FALSE,
                finalized_at = COALESCE(finalized_at, NOW())
            WHERE id = $1 AND user_id = $2
            """,
            session_id,
            user_id,
            error,
        )


async def deactivate_sessions(
    db: Pool,
    user_id: UUID,
    error: Optional[str] = None,
) -> None:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET is_active = FALSE, finalized_at = NOW(), error = $2
            WHERE user_id = $1 AND is_active = TRUE
            """,
            user_id,
            error,
        )


async def claim_stream(db: Pool, session_id: UUID, user_id: UUID, stream_id: UUID) -> Optional[Session]:
    """An atomic lease, shared by all workers; no connection is held during inference."""
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        row = await conn.fetchrow(
            """
            UPDATE sessions
            SET stream_id = $3, stream_lease_expires_at = NOW() + $4 * INTERVAL '1 second',
                recording_limit_seconds = CASE WHEN (SELECT plan FROM account_plans WHERE user_id=$2) = 'paid' THEN $5 ELSE 30 END,
                recording_started_at = clock_timestamp()
            WHERE id = $1 AND user_id = $2 AND is_active = TRUE AND expires_at > NOW()
              AND stream_id IS NULL AND deleting_at IS NULL
            RETURNING *
            """,
            session_id,
            user_id,
            stream_id,
            get_settings().STREAM_LEASE_SECONDS,
            get_settings().MAX_SESSION_DURATION_SECONDS,
        )
    return _row_to_session(row) if row else None


async def refresh_stream(db: Pool, session_id: UUID, stream_id: UUID, *, require_active: bool = True) -> bool:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        row = await conn.fetchrow(
            """UPDATE sessions
               SET stream_lease_expires_at = NOW() + $3 * INTERVAL '1 second'
               WHERE id = $1 AND stream_id = $2
                 AND (NOT $4 OR (is_active = TRUE AND expires_at > NOW() AND stream_lease_expires_at > NOW()))
               RETURNING id""",
            session_id, stream_id, get_settings().STREAM_LEASE_SECONDS, require_active,
        )
    return row is not None


async def finish_stream(db: Pool, session_id: UUID, stream_id: UUID, error: Optional[str] = None) -> bool:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        row = await conn.fetchrow(
            """UPDATE sessions SET is_active = FALSE,
               finalized_at = COALESCE(finalized_at, clock_timestamp()),
               stream_id = NULL, stream_lease_expires_at = NULL,
               error = COALESCE(error, $3)
               WHERE id = $1 AND stream_id = $2 RETURNING id""",
            session_id, stream_id, error,
        )
    return row is not None


async def set_transcript_key(db: Pool, session_id: UUID, user_id: UUID, key: str, text: str | None = None) -> None:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        await conn.execute(
            "UPDATE sessions SET transcript_key=$3, transcript_text=COALESCE($4,transcript_text) WHERE id=$1 AND user_id=$2",
            session_id, user_id, key, text,
        )


async def _account(conn, user_id: UUID) -> AccountOverview:
    plan = await conn.fetchval("SELECT plan FROM account_plans WHERE user_id=$1", user_id) or "free"
    return AccountOverview(plan=plan, recording_limit_seconds=get_settings().MAX_SESSION_DURATION_SECONDS if plan == "paid" else 30)


async def get_account(db: Pool, user_id: UUID) -> AccountOverview:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        return await _account(conn, user_id)


async def record_audio(db: Pool, session_id: UUID, stream_id: UUID, duration_ms: int) -> bool:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        return await conn.fetchval(
            """UPDATE sessions SET recorded_duration_ms=recorded_duration_ms+$3
               WHERE id=$1 AND stream_id=$2 AND is_active=TRUE AND deleting_at IS NULL
                 AND stream_lease_expires_at > NOW()
                 AND recorded_duration_ms+$3 <= recording_limit_seconds*1000
               RETURNING id""", session_id, stream_id, duration_ms,
        ) is not None


async def begin_delete(db: Pool, session_id: UUID, user_id: UUID) -> bool:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        return await conn.fetchval(
            """UPDATE sessions SET deleting_at=clock_timestamp(), is_active=FALSE,
                      finalized_at=COALESCE(finalized_at,clock_timestamp()), stream_id=NULL, stream_lease_expires_at=NULL
               WHERE id=$1 AND user_id=$2
                 AND (stream_id IS NULL OR stream_lease_expires_at <= NOW()) RETURNING id""", session_id, user_id,
        ) is not None


async def delete_session(db: Pool, session_id: UUID, user_id: UUID) -> None:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        await conn.execute("DELETE FROM sessions WHERE id=$1 AND user_id=$2 AND deleting_at IS NOT NULL", session_id, user_id)


async def save_transcript_text(db: Pool, session_id: UUID, user_id: UUID, text: str) -> None:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        await conn.execute("UPDATE sessions SET transcript_text=$3 WHERE id=$1 AND user_id=$2", session_id, user_id, text)
