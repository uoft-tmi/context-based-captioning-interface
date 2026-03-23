from fastapi import APIRouter, Depends

router = APIRouter(prefix="/ws/sessions", tags=["sessions"])


# @router.websocket("/{session_id}/stream")
# async def stream_session_audio(session_id: str, user_id=Depends(get_user_id)):
#     return await session_service.stream_session_audio(
#         session_id=session_id, user_id=user_id
#     )
