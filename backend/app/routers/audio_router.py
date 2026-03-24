import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from supabase import AsyncClient

from app.core.auth import verify_jwt
from app.core.config import get_settings
from app.core.db_dependencies import DBPool
from app.core.supabase_client import get_supabase_client
from app.services import caption_model_service, session_service

router = APIRouter(prefix="/ws/sessions", tags=["sessions"])


@router.websocket("/{session_id}/stream")
async def stream_audio(
    websocket: WebSocket,
    session_id: str,
    db: DBPool,
    supabase: AsyncClient = Depends(get_supabase_client),
):
    await websocket.accept()

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)  # policy violation
        return

    user_id = verify_jwt(token)
    if not user_id:
        await websocket.close(code=1008)  # policy violation
        return

    session = await session_service.get_session(
        db=db, session_id=session_id, user_id=user_id
    )
    if not session or not session.is_active:
        await websocket.close(code=1008)  # policy violation
        return

    transcript_chunks = []
    try:
        while True:
            if session.expires_at < datetime.now(timezone.utc):
                await websocket.send_json({"type": "error", "text": "Session expired"})
                await caption_model_service.finalize(
                    websocket=websocket,
                    session=session,
                    transcript_chunks=transcript_chunks,
                    db=db,
                    supabase_client=supabase,
                )
                await websocket.close(code=4000, reason="Session expired")
                return

            chunk = await asyncio.wait_for(
                websocket.receive_bytes(),
                timeout=get_settings().SESSION_TIMEOUT_SECONDS,
            )

            result = await caption_model_service.transcribe_chunk(
                session=session, audio_chunk=chunk
            )
            transcript_chunks.append(result)

            await websocket.send_json({"type": "caption", "text": result})
    except asyncio.TimeoutError:
        await websocket.send_json(
            {"type": "error", "text": "Session timed out due to inactivity"}
        )
        await caption_model_service.finalize(
            websocket=websocket,
            session=session,
            transcript_chunks=transcript_chunks,
            db=db,
            supabase_client=supabase,
        )
        await websocket.close(code=4000, reason="Session timed out")
        return
    except WebSocketDisconnect:
        await caption_model_service.finalize(
            websocket=websocket,
            session=session,
            transcript_chunks=transcript_chunks,
            db=db,
            supabase_client=supabase,
        )
        return
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return
