from fastapi import APIRouter, Depends, UploadFile

from app.core.auth import get_user_id
from app.database.supabase_client import get_supabase_client
from app.models.session import CreateSessionRequest
from app.services import session_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("")
async def create_session(body: CreateSessionRequest, user_id=Depends(get_user_id)):
    return await session_service.create_session(
        user_id=user_id,
        mode=body.mode,
        pdf_url=body.pdf_url,
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


@router.post("/{session_id}/notes")
async def upload_notes(
    session_id: str,
    file: UploadFile,
    user_id=Depends(get_user_id),
    supabase=Depends(get_supabase_client),
):
    return await session_service.upload_notes(
        session_id=session_id,
        file=file,
        user_id=user_id,
        supabase_client=supabase,
    )


@router.post("/{session_id}/end")
async def end_session(
    session_id: str,
    user_id=Depends(get_user_id),
    supabase_client=Depends(get_supabase_client),
):
    return await session_service.end_session(
        session_id=session_id, user_id=user_id, supabase_client=supabase_client
    )


@router.post("/{session_id}/error")
async def mark_session_error(session_id: str, user_id=Depends(get_user_id)):
    return await session_service.mark_session_error(
        session_id=session_id, user_id=user_id
    )
