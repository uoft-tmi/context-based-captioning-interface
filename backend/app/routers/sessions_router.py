from fastapi import APIRouter, Depends, UploadFile

from app.core.auth import get_user_id
from app.core.session_dependencies import get_session_if_active
from app.database.supabase_client import get_supabase_client
from app.models.session import CreateSessionRequest
from app.services import session_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("")
async def create_session(
    body: CreateSessionRequest,
    user_id=Depends(get_user_id),
    supabase_client=Depends(get_supabase_client),
):
    return await session_service.create_session(
        user_id=user_id, mode=body.mode, supabase_client=supabase_client
    )


@router.get("")
async def get_all_sessions(user_id=Depends(get_user_id)):
    return await session_service.get_all_sessions(user_id=user_id)


@router.get("/active")
async def get_active_session(user_id=Depends(get_user_id)):
    return await session_service.get_active_session(user_id=user_id)


@router.get("/{session_id}")
async def get_session(session_id: str, user_id=Depends(get_user_id)):
    return await session_service.get_session(session_id=session_id, user_id=user_id)


@router.get("/{session_id}/notes")
async def get_session_note(
    session=Depends(get_session_if_active),
    supabase_client=Depends(get_supabase_client),
):
    return await session_service.get_notes(
        session=session,
        supabase_client=supabase_client,
    )


@router.post("/{session_id}/notes")
async def upload_session_note(
    file: UploadFile,
    session=Depends(get_session_if_active),
    supabase_client=Depends(get_supabase_client),
):
    return await session_service.upload_note(
        file=file,
        session=session,
        supabase_client=supabase_client,
    )


@router.delete("/{session_id}/notes")
async def delete_notes(
    filename: str,
    session=Depends(get_session_if_active),
    supabase_client=Depends(get_supabase_client),
):
    return await session_service.delete_note(
        session=session,
        filename=filename,
        supabase_client=supabase_client,
    )


@router.get("/{session_id}/notes/{filename}")
async def download_session_note(
    filename: str,
    session=Depends(get_session_if_active),
    supabase_client=Depends(get_supabase_client),
):
    return await session_service.download_note(
        session=session,
        filename=filename,
        supabase_client=supabase_client,
    )


@router.post("/{session_id}/end")
async def end_session(
    session=Depends(get_session_if_active),
    supabase_client=Depends(get_supabase_client),
):
    return await session_service.end_session(
        session=session, supabase_client=supabase_client
    )


@router.post("/{session_id}/error")
async def mark_session_error(session_id: str, user_id=Depends(get_user_id)):
    return await session_service.mark_session_error(
        session_id=session_id, user_id=user_id
    )


@router.get("/{session_id}/download")
async def download_session_pdf(session_id: str, user_id=Depends(get_user_id)):
    return await session_service.download_session_pdf(
        session_id=session_id, user_id=user_id
    )
