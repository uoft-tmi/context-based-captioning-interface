from typing import Optional

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
    supabase_client: AsyncClient,
) -> Session:
    try:
        await sessions_db.deactivate_sessions(user_id=user_id)
        await cleanup_storage(user_id=user_id, supabase_client=supabase_client)

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


async def get_notes(session: Session, supabase_client: AsyncClient) -> list[str]:
    try:
        session_id = session.id
        user_id = session.user_id
        files = await supabase_client.storage.from_("session-pdfs").list(
            f"{user_id}/{session_id}/"
        )
        return [file["name"] for file in files]
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
        note = await supabase_client.storage.from_("session-pdfs").download(
            f"{user_id}/{session_id}/{filename}"
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

    files = await supabase_client.storage.from_("session-notes").list(path)
    if len(files) >= _settings.MAX_NOTES_PER_SESSION:
        raise HTTPException(
            status_code=400, detail="Maximum number of notes for this session reached"
        )

    contents = await file.read()
    if len(contents) > _settings.MAX_PDF_SIZE:
        raise HTTPException(
            status_code=400, detail="File size exceeds the maximum limit"
        )

    try:
        await supabase_client.storage.from_("session-pdfs").upload(
            (path + filename),
            contents,
            {"content-type": "application/pdf", "upsert": "true"},
        )

        return {"status": "processed"}
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
        await supabase_client.storage.from_("session-notes").remove(
            [f"{user_id}/{session_id}/{filename}"]
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


async def download_session_pdf(
    session_id: str,
    user_id: str,
) -> dict:
    return {}
