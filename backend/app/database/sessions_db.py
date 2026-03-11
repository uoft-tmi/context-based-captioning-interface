from datetime import datetime
from typing import Optional
from uuid import UUID

from app.database.pool import get_pool
from app.models.session import Session, SessionMode


def _row_to_session(row) -> Session:
    return Session(
        id=row["id"],
        user_id=row["user_id"],
        mode=SessionMode(row["mode"]),
        pdf_url=row["pdf_url"],
        status=row["status"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        finalized_at=row["finalized_at"],
        final_transcript=row["final_transcript"],
    )


async def create_session(
    user_id: str,
    mode: str,
    expires_at: datetime,
    pdf_url: Optional[str] = None,
) -> Session:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO sessions (user_id, mode, expires_at, pdf_url)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            UUID(user_id),
            mode,
            expires_at,
            pdf_url,
        )

    return _row_to_session(row)


async def get_session(session_id: str, user_id: str) -> Optional[Session]:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM sessions
            WHERE id = $1 AND user_id = $2
            """,
            UUID(session_id),
            UUID(user_id),
        )

    return _row_to_session(row) if row else None


async def get_active_session(user_id: str) -> Optional[Session]:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM sessions
            WHERE user_id = $1 AND status = 'active'
            """,
            UUID(user_id),
        )

    return _row_to_session(row) if row else None


async def get_all_sessions(user_id: str) -> list[Session]:
    async with get_pool().acquire() as conn:
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


async def update_session_pdf(
    session_id: str, user_id: str, pdf_url: str
) -> Optional[Session]:
    async with get_pool().acquire() as conn:
        row = await conn.execute(
            """
        UPDATE sessions
        SET pdf_url = $1
        WHERE id = $2 AND user_id = $3
        RETURNING *
        """,
            pdf_url,
            UUID(session_id),
            UUID(user_id),
        )
    return _row_to_session(row) if row else None


async def end_session(session_id: str, user_id: str) -> Optional[Session]:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE sessions
            SET status = 'finalized', finalized_at = NOW()
            WHERE id = $1 AND user_id = $2
            RETURNING *
            """,
            UUID(session_id),
            UUID(user_id),
        )
        return _row_to_session(row) if row else None


async def mark_session_error(session_id: str, user_id: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET status = 'error', finalized_at = NOW()
            WHERE id = $1 AND user_id = $2
            """,
            UUID(session_id),
            UUID(user_id),
        )
