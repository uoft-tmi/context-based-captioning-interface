from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from asyncpg import Pool

from app.core.config import get_settings
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
    db: Pool,
    user_id: str,
    mode: str,
) -> Session:
    async with db.acquire() as conn:
        _settings = get_settings()
        current_time = datetime.now()
        row = await conn.fetchrow(
            """
            INSERT INTO sessions (user_id, mode, created_at, expires_at)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            UUID(user_id),
            mode,
            current_time,
            current_time + timedelta(seconds=_settings.MAX_SESSION_DURATION_SECONDS),
        )

    return _row_to_session(row)


async def get_active_session(db: Pool, user_id: str) -> Optional[Session]:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM sessions
            WHERE user_id = $1 AND is_active = TRUE
            AND expires_at > NOW()
            ORDER BY created_at DESC
            LIMIT 1
            """,
            UUID(user_id),
        )

    return _row_to_session(row) if row else None


async def get_session(db: Pool, session_id: str, user_id: str) -> Optional[Session]:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM sessions
            WHERE id = $1 AND user_id = $2
            """,
            UUID(session_id),
            UUID(user_id),
        )

    return _row_to_session(row) if row else None


async def get_all_sessions(db: Pool, user_id: str) -> list[Session]:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM sessions
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            UUID(user_id),
        )

    result = []
    for row in rows:
        session: Session = _row_to_session(row)
        result.append(session)
    return result


async def end_session(db: Pool, session_id: str, user_id: str) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET is_active = FALSE, finalized_at = NOW()
            WHERE id = $1 AND user_id = $2
            """,
            UUID(session_id),
            UUID(user_id),
        )


async def deactivate_sessions(
    db: Pool, user_id: str, error: Optional[str] = None
) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET is_active = FALSE, finalized_at = NOW(), error = $2
            WHERE user_id = $1 AND is_active = FALSE
            """,
            UUID(user_id),
            error,
        )
