from fastapi import APIRouter, Depends, UploadFile

from app.core.auth import get_user_id
from app.core.db_dependencies import DBPool
from app.core.session_dependencies import get_session_if_active
from app.core.supabase_client import get_supabase_client
from app.models.session import CreateSessionRequest
from app.services import session_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("")
async def create_session(
    body: CreateSessionRequest,
    db: DBPool,
    user_id=Depends(get_user_id),
):
    return await session_service.create_session(db=db, user_id=user_id, mode=body.mode)


@router.get("")
async def get_all_sessions(db: DBPool, user_id=Depends(get_user_id)):
    return await session_service.get_all_sessions(db=db, user_id=user_id)


@router.get("/active")
async def get_active_session(db: DBPool, user_id=Depends(get_user_id)):
    return await session_service.get_active_session(db=db, user_id=user_id)


@router.get("/{session_id}")
async def get_session(session_id: str, db: DBPool, user_id=Depends(get_user_id)):
    return await session_service.get_session(
        db=db, session_id=session_id, user_id=user_id
    )


@router.get("/{session_id}/notes")
async def get_session_note(
    db: DBPool,
    session=Depends(get_session_if_active),
):
    return await session_service.get_notes(
        db=db,
        session=session,
    )


@router.post("/{session_id}/notes")
async def upload_session_note(
    file: UploadFile,
    db: DBPool,
    session=Depends(get_session_if_active),
    supabase_client=Depends(get_supabase_client),
):
    return await session_service.upload_note(
        file=file,
        session=session,
        supabase_client=supabase_client,
        db=db,
    )


@router.delete("/{session_id}/notes/{filename}")
async def delete_notes(
    filename: str,
    db: DBPool,
    session=Depends(get_session_if_active),
    supabase_client=Depends(get_supabase_client),
):
    return await session_service.delete_note(
        session=session,
        filename=filename,
        supabase_client=supabase_client,
        db=db,
    )


@router.get("/{session_id}/notes/{filename}")
async def download_session_note(
    filename: str,
    db: DBPool,
    session=Depends(get_session_if_active),
    supabase_client=Depends(get_supabase_client),
):
    return await session_service.download_note(
        session=session,
        filename=filename,
        supabase_client=supabase_client,
        db=db,
    )


@router.post("/{session_id}/end")
async def end_session(
    db: DBPool,
    session=Depends(get_session_if_active),
    supabase_client=Depends(get_supabase_client),
):
    return await session_service.end_session(
        session=session,
        supabase_client=supabase_client,
        db=db,
    )


@router.get("/{session_id}/download")
async def download_session_pdf(
    session_id: str,
    db: DBPool,
    user_id=Depends(get_user_id),
):
    return await session_service.download_session_transcript(
        session_id=session_id,
        user_id=user_id,
        db=db,
    )
