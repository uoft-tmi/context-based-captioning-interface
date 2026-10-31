from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, HTTPException

from app.core.auth import get_user_id
from app.core.dependencies import Sessions
from app.models.session import Session


async def get_session_if_active(
    session_id: UUID,
    sessions: Sessions,
    user_id: UUID = Depends(get_user_id),
) -> Session:
    session = await sessions.get(session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.is_active:
        raise HTTPException(status_code=410, detail="Session ended")
    if session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Session expired")
    return session


async def get_session_if_owned(session_id: UUID, sessions: Sessions, user_id: UUID = Depends(get_user_id)) -> Session:
    session = await sessions.get(session_id, user_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    return session
