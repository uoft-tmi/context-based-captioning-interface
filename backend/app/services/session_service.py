from typing import Optional

from fastapi import HTTPException, UploadFile
from supabase import AsyncClient

from app.core.config import get_settings
from app.database import sessions_db
from app.models.session import Session, SessionMode
from app.services.storage_helper import cleanup_storage

_settings = get_settings()


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

        return await sessions_db.create_session(
            user_id=user_id,
            mode=mode,
            pdf_url=pdf_url,
        )
    except HTTPException:
        raise
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_all_sessions(
    user_id: str,
) -> list[Session]:
    try:
        return await sessions_db.get_all_sessions(user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_active_session(
    user_id: str,
) -> Optional[Session]:
    try:
        session = await sessions_db.get_active_session(user_id=user_id)
        return session
    except HTTPException:
        raise
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def upload_notes(
    session_id: str,
    file: UploadFile,
    user_id: str,
    supabase_client: AsyncClient,
) -> dict:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    contents = await file.read()
    if len(contents) > _settings.MAX_PDF_SIZE:
        raise HTTPException(
            status_code=400, detail="File size exceeds the maximum limit"
        )

    path = f"{user_id}/{session_id}.pdf"

    try:
        await supabase_client.storage.from_("session-pdfs").upload(
            path, contents, {"content-type": "application/pdf"}
        )

        await sessions_db.update_session_pdf(
            session_id=session_id,
            user_id=user_id,
            pdf_url=f"{path}",
        )

        return {"status": "processed", "pdf_url": path}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def end_session(
    session_id: str,
    user_id: str,
    supabase_client: AsyncClient,
) -> dict:
    try:
        session = await sessions_db.end_session(
            session_id=session_id,
            user_id=user_id,
        )

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        await cleanup_storage(user_id, supabase_client)

        return {"message": "Session ended successfully", "session": session}
    except HTTPException:
        raise
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
