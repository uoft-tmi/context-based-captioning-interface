from typing import Optional
from uuid import UUID

from asyncpg import Pool


# ----------------- Session Notes -----------------
async def save_note(
    db: Pool,
    session_id: UUID,
    user_id: UUID,
    filename: str,
    storage_key: str,
) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO session_notes (user_id, session_id, filename, storage_key)
            VALUES ($1, $2, $3, $4)
            """,
            user_id,
            session_id,
            filename,
            storage_key,
        )


async def get_note(
    db: Pool, session_id: UUID, user_id: UUID, filename: str
) -> Optional[str]:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT storage_key FROM session_notes
            WHERE session_id = $1 AND user_id = $2 AND filename = $3
            """,
            session_id,
            user_id,
            filename,
        )

    return row["storage_key"] if row else None


async def list_notes(db: Pool, session_id: UUID, user_id: UUID) -> list[str]:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT filename FROM session_notes
            WHERE session_id = $1 AND user_id = $2
            """,
            session_id,
            user_id,
        )

    return [row["filename"] for row in rows]


async def delete_note(db: Pool, session_id: UUID, user_id: UUID, filename: str) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM session_notes
            WHERE session_id = $1 AND user_id = $2 AND filename = $3
            """,
            session_id,
            user_id,
            filename,
        )


async def delete_all_notes(db: Pool, session_id: UUID, user_id: UUID) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM session_notes
            WHERE session_id = $1 AND user_id = $2
            """,
            session_id,
            user_id,
        )


async def count_notes(db: Pool, session_id: UUID) -> int:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) FROM session_notes
            WHERE session_id = $1
            """,
            session_id,
        )

    return row["count"] if row else 0
