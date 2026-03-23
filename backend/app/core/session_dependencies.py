from datetime import datetime, timezone

from fastapi import Depends, HTTPException

from app.core.auth import get_user_id
from app.database import sessions_db
from app.models.session import Session


async def get_session_if_active(
    session_id: str,
    user_id: str = Depends(get_user_id),
) -> Session:
    session = await sessions_db.get_session(session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.status == "active":
        raise HTTPException(status_code=410, detail="Session ended")
    if session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Session expired")
    return session
