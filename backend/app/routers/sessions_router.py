from uuid import UUID

from app.core.auth import get_user_id
from app.core.dependencies import Notes, Objects, Sessions
from app.core.session_dependencies import get_session_if_active, get_session_if_owned
from app.models.session import CreateSessionRequest, SessionErrorRequest
from app.services import session_service
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from app.core.dependencies import get_transcription_provider
from app.ports.captioning import TranscriptionProvider

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("")
async def create_session(
    body: CreateSessionRequest,
    sessions: Sessions,
    user_id: UUID = Depends(get_user_id),
    provider: TranscriptionProvider = Depends(get_transcription_provider),
):
    if body.mode == "context" and not provider.capabilities.supports_pdf_notes:
        raise HTTPException(400, "The selected provider supports audio-only sessions. Choose a provider with lecture-note support.")
    return await session_service.create_session(sessions=sessions, user_id=user_id, mode=body.mode, name=body.name)


@router.get("")
async def get_all_sessions(sessions: Sessions, user_id: UUID = Depends(get_user_id)):
    return await session_service.get_all_sessions(sessions=sessions, user_id=user_id)


@router.get("/active")
async def get_active_session(sessions: Sessions, user_id: UUID = Depends(get_user_id)):
    return await session_service.get_active_session(sessions=sessions, user_id=user_id)


@router.get("/{session_id}")
async def get_session(
    session_id: UUID,
    sessions: Sessions,
    user_id: UUID = Depends(get_user_id),
):
    return await session_service.get_session(
        sessions=sessions, session_id=session_id, user_id=user_id
    )


@router.get("/{session_id}/notes")
async def get_session_note(
    notes: Notes,
    session=Depends(get_session_if_owned),
):
    return await session_service.get_notes(
        notes=notes,
        session=session,
    )


@router.post("/{session_id}/notes")
async def upload_session_note(
    file: UploadFile,
    notes: Notes,
    objects: Objects,
    session=Depends(get_session_if_active),
    provider: TranscriptionProvider = Depends(get_transcription_provider),
):
    return await session_service.upload_note(
        file=file,
        session=session,
        objects=objects,
        notes=notes,
        require_text=session.mode == "context" and provider.capabilities.requires_text_notes,
    )


@router.delete("/{session_id}/notes/{filename}")
async def delete_notes(
    filename: str,
    notes: Notes,
    objects: Objects,
    session=Depends(get_session_if_owned),
):
    return await session_service.delete_note(
        session=session,
        filename=filename,
        objects=objects,
        notes=notes,
    )


@router.get("/{session_id}/notes/{filename}")
async def download_session_note(
    filename: str,
    notes: Notes,
    objects: Objects,
    session=Depends(get_session_if_owned),
):
    return await session_service.download_note(
        session=session,
        filename=filename,
        objects=objects,
        notes=notes,
    )


@router.post("/{session_id}/end")
async def end_session(
    session_id: UUID,
    sessions: Sessions,
    objects: Objects,
    notes: Notes,
    user_id: UUID = Depends(get_user_id),
):
    session = await session_service.get_session(
        sessions=sessions,
        session_id=session_id,
        user_id=user_id,
    )
    return await session_service.end_session(
        session=session,
        objects=objects,
        notes=notes,
        sessions=sessions,
    )


@router.post("/{session_id}/error")
@router.post("/{session_id}/errors")
async def mark_session_error(
    session_id: UUID,
    payload: SessionErrorRequest,
    sessions: Sessions,
    objects: Objects,
    notes: Notes,
    user_id: UUID = Depends(get_user_id),
):
    session = await session_service.get_session(
        sessions=sessions,
        session_id=session_id,
        user_id=user_id,
    )
    return await session_service.mark_session_error(
        session=session,
        payload=payload,
        objects=objects,
        notes=notes,
        sessions=sessions,
    )


@router.get("/{session_id}/download")
async def download_session_pdf(
    session_id: UUID,
    sessions: Sessions,
    objects: Objects,
    user_id: UUID = Depends(get_user_id),
):
    return await session_service.download_session_transcript(
        session_id=session_id,
        user_id=user_id,
        sessions=sessions,
        objects=objects,
    )


@router.delete("/{session_id}")
async def delete_session(session_id: UUID, sessions: Sessions, notes: Notes, objects: Objects, user_id: UUID = Depends(get_user_id)):
    return await session_service.delete_session(session_id, user_id, sessions, notes, objects)
