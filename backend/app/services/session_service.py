from typing import Optional
from uuid import uuid4

import asyncpg
from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from supabase import AsyncClient

from app.core.config import get_settings
from app.database import sessions_db
from app.models.session import Session, SessionMode
from app.services.storage_helper import cleanup_storage

_settings = get_settings()


async def create_session(
    user_id: str,
    mode: SessionMode,
) -> Session:
    try:
        await sessions_db.deactivate_sessions(user_id=user_id)

        return await sessions_db.create_session(
            user_id=user_id,
            mode=mode,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_active_session(
    user_id: str,
) -> Optional[Session]:
    try:
        return await sessions_db.get_active_session(user_id=user_id)
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


async def get_notes(session: Session) -> list[str]:
    try:
        session_id = session.id
        user_id = session.user_id
        return await sessions_db.list_notes(session_id=session_id, user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def download_note(
    session: Session, filename: str, supabase_client: AsyncClient
) -> StreamingResponse:
    try:
        session_id = session.id
        user_id = session.user_id
        file_key = await sessions_db.get_note(
            session_id=session_id, user_id=user_id, filename=filename
        )

        if not file_key:
            raise HTTPException(status_code=404, detail=f"{filename} not found")

        note = await supabase_client.storage.from_("session-pdfs").download(
            f"{user_id}/{session_id}/{file_key}"
        )

        if not note:
            raise HTTPException(status_code=404, detail=f"{filename} not found")

        return StreamingResponse(
            iter([note]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def upload_note(
    file: UploadFile,
    session: Session,
    supabase_client: AsyncClient,
) -> dict:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    filename = file.filename
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Filename must end with .pdf")

    session_id = session.id
    user_id = session.user_id
    path = f"{user_id}/{session_id}/"

    count = await sessions_db.count_notes(session_id=session_id)
    if count >= _settings.MAX_NOTES_PER_SESSION:
        raise HTTPException(
            status_code=400, detail="Maximum number of notes for this session reached"
        )

    contents = await file.read()
    if len(contents) > _settings.MAX_PDF_SIZE:
        raise HTTPException(
            status_code=400, detail="File size exceeds the maximum limit"
        )

    try:
        file_key = uuid4().hex + ".pdf"

        await sessions_db.save_note(
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            storage_key=file_key,
        )

        await supabase_client.storage.from_("session-pdfs").upload(
            (path + file_key),
            contents,
            {"content-type": "application/pdf", "upsert": "true"},
        )

        return {"status": "processed"}
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=409, detail="A note with this filename already exists"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def delete_note(
    filename: str,
    session: Session,
    supabase_client: AsyncClient,
):
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    try:
        user_id = session.user_id
        session_id = session.id
        file_key = await sessions_db.get_note(
            session_id=session_id, user_id=user_id, filename=filename
        )
        if not file_key:
            raise HTTPException(status_code=404, detail=f"{filename} not found")
        await supabase_client.storage.from_("session-pdfs").remove(
            [f"{user_id}/{session_id}/{file_key}"]
        )
        await sessions_db.delete_note(
            session_id=session_id, user_id=user_id, filename=filename
        )

        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def end_session(
    session: Session,
    supabase_client: AsyncClient,
) -> dict:
    try:
        session_id = str(session.id)
        user_id = str(session.user_id)
        await sessions_db.end_session(session_id=session_id, user_id=user_id)

        await cleanup_storage(
            user_id=user_id, session_id=session_id, supabase_client=supabase_client
        )

        return {"message": "Session ended successfully", "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def download_session_transcript(
    session_id: str,
    user_id: str,
) -> dict:
    return {"transcript": "Transcript download not implemented yet"}
