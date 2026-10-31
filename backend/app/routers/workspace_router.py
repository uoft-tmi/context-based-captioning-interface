from uuid import UUID

from fastapi import APIRouter, Depends
from app.core.auth import get_user_id
from app.core.dependencies import Notes, Sessions

router = APIRouter(prefix="/api", tags=["workspace"])


@router.get("/account")
async def account(sessions: Sessions, user_id: UUID = Depends(get_user_id)):
    return await sessions.get_account(user_id)


@router.get("/library")
async def library(notes: Notes, user_id: UUID = Depends(get_user_id)):
    return await notes.list_library(user_id)
