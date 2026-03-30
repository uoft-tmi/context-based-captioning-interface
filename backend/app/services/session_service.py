from typing import Optional
from uuid import UUID, uuid4

from asyncpg import UniqueViolationError
from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from supabase import AsyncClient

from app.core.config import get_settings
from app.core.db_dependencies import DBPool
from app.database import notes_db, sessions_db
from app.models.session import Session, SessionMode
from app.utils.storage_helper import cleanup_storage

_settings = get_settings()


async def create_session(db: DBPool, user_id: UUID, mode: SessionMode) -> Session:
    try:
        await sessions_db.deactivate_sessions(db=db, user_id=user_id)
        return await sessions_db.create_session(
            db=db,
            user_id=user_id,
            mode=mode,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_active_session(db: DBPool, user_id: UUID) -> Optional[Session]:
    try:
        return await sessions_db.get_active_session(db=db, user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_session(
    db: DBPool,
    session_id: UUID,
    user_id: UUID,
) -> Session:
    try:
        session = await sessions_db.get_session(
            db=db, session_id=session_id, user_id=user_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_all_sessions(
    db: DBPool,
    user_id: UUID,
) -> list[Session]:
    try:
        return await sessions_db.get_all_sessions(db=db, user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_notes(db: DBPool, session: Session) -> list[str]:
    try:
        session_id = session.id
        user_id = session.user_id
        return await notes_db.list_notes(db=db, session_id=session_id, user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def download_note(
    session: Session, filename: str, supabase_client: AsyncClient, db: DBPool
) -> StreamingResponse:
    try:
        session_id = session.id
        user_id = session.user_id
        file_key = await notes_db.get_note(
            db=db, session_id=session_id, user_id=user_id, filename=filename
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
    db: DBPool,
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

    count = await notes_db.count_notes(db=db, session_id=session_id)
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

        await notes_db.save_note(
            db=db,
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
    except UniqueViolationError:
        raise HTTPException(
            status_code=409, detail="A note with this filename already exists"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def delete_note(
    filename: str, session: Session, supabase_client: AsyncClient, db: DBPool
):
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    try:
        user_id = session.user_id
        session_id = session.id
        file_key = await notes_db.get_note(
            db=db, session_id=session_id, user_id=user_id, filename=filename
        )
        if not file_key:
            raise HTTPException(status_code=404, detail=f"{filename} not found")
        await supabase_client.storage.from_("session-pdfs").remove(
            [f"{user_id}/{session_id}/{file_key}"]
        )
        await notes_db.delete_note(
            db=db, session_id=session_id, user_id=user_id, filename=filename
        )

        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def end_session(
    session: Session, supabase_client: AsyncClient, db: DBPool
) -> dict:
    try:
        session_id = session.id
        user_id = session.user_id
        await sessions_db.end_session(db=db, session_id=session_id, user_id=user_id)

        await cleanup_storage(
            user_id=user_id,
            session_id=session_id,
            supabase_client=supabase_client,
            db=db,
        )

        return {"message": "Session ended successfully", "session_id": str(session_id)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def download_session_transcript(
    session_id: UUID,
    user_id: UUID,
    db: DBPool,
) -> dict:
    return {"transcript": "Transcript download not implemented yet"}


async def slide_expiry(db: DBPool, session_id: UUID):
    try:
        await sessions_db.slide_expiry(db=db, session_id=session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
