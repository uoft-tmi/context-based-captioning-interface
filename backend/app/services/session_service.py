import json
import logging
from typing import Optional
from uuid import UUID, uuid4
from urllib.parse import quote

from app.core.config import get_settings
from app.utils.pdf_helper import transcript_to_pdf_bytes
from app.utils.note_context import pdf_vocabulary
from starlette.concurrency import run_in_threadpool
from app.models.session import Session, SessionErrorRequest, SessionMode
from app.ports.persistence import NotesRepository, ObjectStore, PersistenceConflictError, SessionRepository
from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse

_settings = get_settings()
logger = logging.getLogger(__name__)


async def create_session(sessions: SessionRepository, user_id: UUID, mode: SessionMode, name: str) -> Session:
    try:
        return await sessions.create_session(
            user_id=user_id,
            mode=mode,
            name=name,
        )

    except PersistenceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_active_session(sessions: SessionRepository, user_id: UUID) -> Optional[Session]:
    try:
        return await sessions.get_active_session(user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_session(
    sessions: SessionRepository,
    session_id: UUID,
    user_id: UUID,
) -> Session:
    try:
        session = await sessions.get(
            session_id=session_id, user_id=user_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_all_sessions(
    sessions: SessionRepository,
    user_id: UUID,
) -> list[Session]:
    try:
        return await sessions.get_all_sessions(user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_notes(notes: NotesRepository, session: Session) -> list[str]:
    try:
        session_id = session.id
        user_id = session.user_id
        return await notes.list_notes(session_id=session_id, user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def download_note(
    session: Session, filename: str, objects: ObjectStore, notes: NotesRepository
) -> StreamingResponse:
    try:
        session_id = session.id
        user_id = session.user_id
        file_key = await notes.get_note(
            session_id=session_id, user_id=user_id, filename=filename
        )

        if not file_key:
            raise HTTPException(status_code=404, detail=f"{filename} not found")

        note = await objects.get("session-pdfs",
            f"{user_id}/{session_id}/{file_key}"
        )

        if not note:
            raise HTTPException(status_code=404, detail=f"{filename} not found")

        return StreamingResponse(
            iter([note]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def upload_note(
    file: UploadFile,
    session: Session,
    objects: ObjectStore,
    notes: NotesRepository,
    require_text: bool = False,
) -> dict:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    filename = file.filename
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    if any(character in filename for character in ("/", "\\", "\r", "\n")):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Filename must end with .pdf")

    session_id = session.id
    user_id = session.user_id
    path = f"{user_id}/{session_id}/"

    count = await notes.count_notes(session_id=session_id)
    if count >= _settings.MAX_NOTES_PER_SESSION:
        raise HTTPException(
            status_code=400, detail="Maximum number of notes for this session reached"
        )

    contents = await file.read(_settings.MAX_PDF_SIZE + 1)
    if len(contents) > _settings.MAX_PDF_SIZE:
        raise HTTPException(
            status_code=400, detail="File size exceeds the maximum limit"
        )

    if require_text:
        try:
            await run_in_threadpool(pdf_vocabulary, contents)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        file_key = uuid4().hex + ".pdf"

        await objects.put("session-pdfs",
            (path + file_key),
            contents,
            content_type="application/pdf",
        )
        try:
            await notes.save_note(
                session_id=session_id,
                user_id=user_id,
                filename=filename,
                storage_key=file_key,
            )
        except Exception:
            try:
                await objects.delete("session-pdfs", [path + file_key])
            except Exception:
                logger.exception("Unable to remove orphan note upload for session %s", session_id)
            raise

        return {"status": "uploaded"}
    except PersistenceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def delete_note(
    filename: str, session: Session, objects: ObjectStore, notes: NotesRepository
):
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    try:
        user_id = session.user_id
        session_id = session.id
        file_key = await notes.get_note(
            session_id=session_id, user_id=user_id, filename=filename
        )
        if not file_key:
            raise HTTPException(status_code=404, detail=f"{filename} not found")
        await objects.delete("session-pdfs",
            [f"{user_id}/{session_id}/{file_key}"]
        )
        await notes.delete_note(
            session_id=session_id, user_id=user_id, filename=filename
        )

        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def mark_session_error(
    session: Session,
    payload: SessionErrorRequest,
    objects: ObjectStore,
    notes: NotesRepository,
    sessions: SessionRepository,
) -> dict:
    try:
        session_id = session.id
        user_id = session.user_id
        error_payload = {
            "reason": payload.reason,
            "details": payload.details,
            "source": payload.source,
        }
        error_text = json.dumps(error_payload, ensure_ascii=True)

        await sessions.mark_session_error(
            session_id=session_id,
            user_id=user_id,
            error=error_text,
        )

        # Uploaded files are retained in the library until explicit deletion.

        return {
            "message": "Session marked as error",
            "session_id": str(session_id),
            "error": error_text,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def end_session(
    session: Session, objects: ObjectStore, sessions: SessionRepository, notes: NotesRepository
) -> dict:
    try:
        session_id = session.id
        user_id = session.user_id
        ended = await sessions.end_session(session_id=session_id, user_id=user_id)
        if not ended:
            raise HTTPException(status_code=409, detail="Stop the active stream before ending the session.")

        # Uploaded files are retained in the library until explicit deletion.

        return {"message": "Session ended successfully", "session_id": str(session_id)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def download_session_transcript(
    session_id: UUID,
    user_id: UUID,
    sessions: SessionRepository,
    objects: ObjectStore,
) -> StreamingResponse:
    try:
        session = await sessions.get(
            session_id=session_id,
            user_id=user_id,
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if not session.transcript_key:
            if session.transcript_text is None:
                raise HTTPException(status_code=404, detail="Transcript not available")
            payload = await run_in_threadpool(transcript_to_pdf_bytes, session.transcript_text, title=session.name, created_at=session.created_at, duration_ms=session.recorded_duration_ms)
        else:
            payload = await objects.get("transcripts", session.transcript_key)

        if not payload:
            raise HTTPException(status_code=404, detail="Transcript not available")

        is_pdf = not session.transcript_key or session.transcript_key.lower().endswith(".pdf")
        filename = (
            f"{session.name}.pdf" if is_pdf else f"{session.name}.txt"
        )
        media_type = "application/pdf" if is_pdf else "text/plain"

        return StreamingResponse(
            iter([payload]),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def delete_session(session_id: UUID, user_id: UUID, sessions: SessionRepository, notes: NotesRepository, objects: ObjectStore) -> dict:
    session = await get_session(sessions, session_id, user_id)
    if not await sessions.begin_delete(session_id, user_id):
        raise HTTPException(409, "Stop the recording before deleting this session.")
    try:
        keys = await notes.list_note_storage_keys(session_id, user_id)
        await objects.delete("session-pdfs", [f"{user_id}/{session_id}/{key}" for key in keys])
        if session.transcript_key:
            await objects.delete("transcripts", [session.transcript_key])
        await sessions.delete_session(session_id, user_id)
    except Exception as exc:
        logger.exception("Session deletion incomplete for %s", session_id)
        raise HTTPException(503, "Deletion is incomplete. Your session remains listed; retry deletion.") from exc
    return {"status": "deleted"}
