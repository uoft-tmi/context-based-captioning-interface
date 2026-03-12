from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException

from app.core.config import get_settings
from app.database import sessions_db
from app.database.supabase_client import get_supabase_client
from app.models.session import Session, SessionMode

_settings = get_settings()
supabase_client = get_supabase_client()


async def cleanup_storage(user_id: str):
    try:
        res = await supabase_client.storage.from_("avatars").list(
            user_id,
            {
                "limit": 100,
                "offset": 0,
                "sortBy": {"column": "name", "order": "desc"},
            },
        )
        filenames = [file["name"] for file in res if file["name"]]
        for filename in filenames:
            await supabase_client.storage.from_("avatars").remove(
                [f"{user_id}/{filename}"]
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def create_session(
    user_id: str,
    mode: SessionMode,
    pdf_url: Optional[str] = None,
) -> Session:
    try:
        existing = await sessions_db.get_active_session(user_id=user_id)

        if existing:
            raise HTTPException(
                status_code=409, detail="An active session already exists for this user"
            )

        expires_at = datetime.now() + timedelta(
            seconds=_settings.MAX_SESSION_DURATION_SECONDS
        )

        return await sessions_db.create_session(
            user_id=user_id,
            mode=mode,
            expires_at=expires_at,
            pdf_url=pdf_url,
        )
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


async def get_upload_link(userid: str, filename: str) -> str:
    try:
        res = await supabase_client.storage.from_(
            "pdf-uploads"
        ).create_signed_upload_url(f"{userid}/{filename}")
        return res.get("signed_url")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def end_session(
    session_id: str,
    user_id: str,
) -> dict:
    try:
        session = await sessions_db.end_session(
            session_id=session_id,
            user_id=user_id,
        )

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        await cleanup_storage(user_id)

        return {"message": "Session ended successfully", "session": session}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def mark_session_error(
    session_id: str,
    user_id: str,
) -> dict:
    try:
        await sessions_db.mark_session_error(
            session_id=session_id,
            user_id=user_id,
        )
        return {"message": "Session marked as error successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
