"""The same SQL adapters work with Supabase, Neon, or other PostgreSQL hosts."""
from uuid import UUID

from app.adapters.stream_sessions import PostgresStreamSessions
from app.database import notes_db, sessions_db
from app.models.session import AccountOverview, LibraryFile, Session
from app.ports.persistence import PersistenceConflictError
from asyncpg import Pool, UniqueViolationError


class PostgresSessionRepository(PostgresStreamSessions):
    async def create_session(self, user_id: UUID, mode: str, name: str | None = None) -> Session:
        try:
            return await sessions_db.create_session(self._db, user_id, mode, name)
        except UniqueViolationError as exc:
            raise PersistenceConflictError("A session with this name already exists" if exc.constraint_name == "sessions_unique_name_per_user" else "An active session already exists. End it before creating another.") from exc

    async def get_active_session(self, user_id: UUID) -> Session | None:
        return await sessions_db.get_active_session(self._db, user_id)

    async def get_all_sessions(self, user_id: UUID) -> list[Session]:
        return await sessions_db.get_all_sessions(self._db, user_id)

    async def end_session(self, session_id: UUID, user_id: UUID) -> bool:
        return await sessions_db.end_session(self._db, session_id, user_id)

    async def mark_session_error(self, session_id: UUID, user_id: UUID, error: str) -> None:
        await sessions_db.mark_session_error(self._db, session_id, user_id, error)

    async def save_transcript_text(self, session_id: UUID, user_id: UUID, text: str) -> None:
        await sessions_db.save_transcript_text(self._db, session_id, user_id, text)

    async def set_transcript_key(self, session_id: UUID, user_id: UUID, key: str, text: str | None = None) -> None:
        await sessions_db.set_transcript_key(self._db, session_id, user_id, key, text)

    async def get_account(self, user_id: UUID) -> AccountOverview:
        return await sessions_db.get_account(self._db, user_id)

    async def begin_delete(self, session_id: UUID, user_id: UUID) -> bool:
        return await sessions_db.begin_delete(self._db, session_id, user_id)

    async def delete_session(self, session_id: UUID, user_id: UUID) -> None:
        await sessions_db.delete_session(self._db, session_id, user_id)


class PostgresNotesRepository:
    def __init__(self, db: Pool):
        self._db = db

    async def list_library(self, user_id: UUID) -> list[LibraryFile]:
        return await notes_db.list_library(self._db, user_id)

    async def save_note(self, session_id: UUID, user_id: UUID, filename: str, storage_key: str) -> None:
        try:
            await notes_db.save_note(self._db, session_id, user_id, filename, storage_key)
        except UniqueViolationError as exc:
            raise PersistenceConflictError("A note with this filename already exists") from exc

    async def get_note(self, session_id: UUID, user_id: UUID, filename: str) -> str | None:
        return await notes_db.get_note(self._db, session_id, user_id, filename)

    async def list_notes(self, session_id: UUID, user_id: UUID) -> list[str]:
        return await notes_db.list_notes(self._db, session_id, user_id)

    async def list_note_storage_keys(self, session_id: UUID, user_id: UUID) -> list[str]:
        return await notes_db.list_note_storage_keys(self._db, session_id, user_id)

    async def delete_note(self, session_id: UUID, user_id: UUID, filename: str) -> None:
        await notes_db.delete_note(self._db, session_id, user_id, filename)

    async def delete_all_notes(self, session_id: UUID, user_id: UUID) -> None:
        await notes_db.delete_all_notes(self._db, session_id, user_id)

    async def count_notes(self, session_id: UUID) -> int:
        return await notes_db.count_notes(self._db, session_id)
