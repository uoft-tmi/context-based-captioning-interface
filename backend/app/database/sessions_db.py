from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from app.core.config import get_settings
from app.core.db_dependencies import DBPool
from app.models.session import Session, SessionMode


# ----------------- Helper Functions -----------------
def _row_to_session(row) -> Session:
    return Session(
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
async def create_session(
    db: DBPool,
    user_id: UUID,
    mode: str,
) -> Session:
    async with db.acquire() as conn:
        _settings = get_settings()
        current_time = datetime.now(timezone.utc)
        row = await conn.fetchrow(
            """
            INSERT INTO sessions (user_id, mode, created_at, expires_at)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            user_id,
            mode,
            current_time,
            current_time + timedelta(seconds=_settings.MAX_SESSION_DURATION_SECONDS),
        )

    return _row_to_session(row)


async def get_active_session(db: DBPool, user_id: UUID) -> Optional[Session]:
    async with db.acquire() as conn:
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
    db: DBPool,
    session_id: UUID,
    user_id: UUID,
) -> Optional[Session]:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM sessions
            WHERE id = $1 AND user_id = $2
            """,
            session_id,
            user_id,
        )

    return _row_to_session(row) if row else None


async def get_all_sessions(db: DBPool, user_id: UUID) -> list[Session]:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM sessions
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )
    return [_row_to_session(row) for row in rows]


async def end_session(db: DBPool, session_id: UUID, user_id: UUID) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET is_active = FALSE, finalized_at = NOW()
            WHERE id = $1 AND user_id = $2
            """,
            session_id,
            user_id,
        )


async def deactivate_sessions(
    db: DBPool,
    user_id: UUID,
    error: Optional[str] = None,
) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET is_active = FALSE, finalized_at = NOW(), error = $2
            WHERE user_id = $1 AND is_active = TRUE
            """,
            user_id,
            error,
        )


async def slide_expiry(db: DBPool, session_id: UUID) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET expires_at = NOW() + INTERVAL '1 second' * $2
            WHERE id = $1
            """,
            session_id,
            get_settings().EXPIRY_SLIDE_SECONDS,
        )
