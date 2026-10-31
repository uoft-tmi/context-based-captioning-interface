from app.core.config import get_settings
from typing import Optional
from uuid import UUID

from asyncpg import Pool
from app.models.session import LibraryFile
from app.ports.persistence import PersistenceConflictError


# ----------------- Session Notes -----------------
async def save_note(
    db: Pool,
    session_id: UUID,
    user_id: UUID,
    filename: str,
    storage_key: str,
) -> None:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        inserted = await conn.fetchval(
            """
            INSERT INTO session_notes (user_id, session_id, filename, storage_key)
            SELECT $1, $2, $3, $4 FROM sessions
            WHERE id=$2 AND user_id=$1 AND is_active=TRUE AND stream_id IS NULL AND deleting_at IS NULL
            RETURNING id
            """,
            user_id,
            session_id,
            filename,
            storage_key,
        )
        if inserted is None:
            raise PersistenceConflictError("This session no longer accepts uploads")


async def get_note(
    db: Pool, session_id: UUID, user_id: UUID, filename: str
) -> Optional[str]:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
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
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        rows = await conn.fetch(
            """
            SELECT filename FROM session_notes
            WHERE session_id = $1 AND user_id = $2
            """,
            session_id,
            user_id,
        )

    return [row["filename"] for row in rows]


async def list_note_storage_keys(
    db: Pool,
    session_id: UUID,
    user_id: UUID,
) -> list[str]:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        rows = await conn.fetch(
            """
            SELECT storage_key FROM session_notes
            WHERE session_id = $1 AND user_id = $2
            ORDER BY created_at ASC
            """,
            session_id,
            user_id,
        )

    return [row["storage_key"] for row in rows]


async def delete_note(
    db: Pool, session_id: UUID, user_id: UUID, filename: str
) -> None:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
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
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        await conn.execute(
            """
            DELETE FROM session_notes
            WHERE session_id = $1 AND user_id = $2
            """,
            session_id,
            user_id,
        )


async def count_notes(db: Pool, session_id: UUID) -> int:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) FROM session_notes
            WHERE session_id = $1
            """,
            session_id,
        )

    return row["count"] if row else 0


async def list_library(db: Pool, user_id: UUID) -> list[LibraryFile]:
    async with db.acquire(timeout=get_settings().DB_ACQUIRE_TIMEOUT_SECONDS) as conn:
        rows = await conn.fetch(
            """SELECT n.id,n.session_id,s.name AS session_name,n.filename,n.created_at
               FROM session_notes n JOIN sessions s ON s.id=n.session_id AND s.user_id=n.user_id
               WHERE n.user_id=$1 ORDER BY s.created_at DESC,n.created_at ASC""", user_id,
        )
    return [LibraryFile(**dict(row)) for row in rows]
