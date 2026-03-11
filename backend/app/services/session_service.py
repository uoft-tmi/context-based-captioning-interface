from datetime import datetime
from typing import Optional

from fastapi import HTTPException

from app.database import sessions_db
from app.models.session import Session, SessionMode


async def create_session(
    user_id: str,
    mode: SessionMode,
    expires_at: datetime,
    pdf_url: Optional[str] = None,
) -> Session:
    try:
        session = await sessions_db.create_session(
            user_id=user_id,
            mode=mode,
            expires_at=expires_at,
            pdf_url=pdf_url,
        )
        return session
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_session(
    session_id: str,
    user_id: str,
) -> Session:
    try:
        session = await sessions_db.get_session(session_id=session_id, user_id=user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_all_sessions(
    user_id: str,
) -> list[Session]:
    try:
        return await sessions_db.get_all_sessions(user_id=user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_active_session(
    user_id: str,
) -> Optional[Session]:
    try:
        session = await sessions_db.get_active_session(user_id=user_id)
        return session
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def update_session_pdf(
    session_id: str,
    user_id: str,
    pdf_url: str,
) -> Session:
    try:
        session = await sessions_db.update_session_pdf(
            session_id=session_id,
            user_id=user_id,
            pdf_url=pdf_url,
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def end_session(
    session_id: str,
    user_id: str,
) -> Session:
    try:
        session = await sessions_db.end_session(
            session_id=session_id,
            user_id=user_id,
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def mark_session_error(
    session_id: str,
    user_id: str,
) -> None:
    try:
        await sessions_db.mark_session_error(
            session_id=session_id,
            user_id=user_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
