from uuid import UUID

import asyncpg
from app.database import sessions_db
from app.models.session import Session


class PostgresStreamSessions:
    def __init__(self, db: asyncpg.Pool):
        self._db = db

    async def record_audio(self, session_id: UUID, stream_id: UUID, duration_ms: int) -> bool:
        return await sessions_db.record_audio(self._db, session_id, stream_id, duration_ms)

    async def get(self, session_id: UUID, user_id: UUID) -> Session | None:
        return await sessions_db.get_session(self._db, session_id, user_id)

    async def claim(self, session_id: UUID, user_id: UUID, stream_id: UUID) -> Session | None:
        return await sessions_db.claim_stream(self._db, session_id, user_id, stream_id)

    async def refresh(self, session_id: UUID, stream_id: UUID, *, require_active: bool = True) -> bool:
        return await sessions_db.refresh_stream(self._db, session_id, stream_id, require_active=require_active)

    async def finish(self, session_id: UUID, stream_id: UUID, error: str | None = None) -> bool:
        return await sessions_db.finish_stream(self._db, session_id, stream_id, error)
