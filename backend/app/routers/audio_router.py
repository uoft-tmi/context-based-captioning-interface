import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from supabase import AsyncClient

from app.clients.caption_model_client import ModelClient
from app.clients.supabase_client import get_supabase_client
from app.core.auth import verify_jwt
from app.core.config import get_settings
from app.core.db_dependencies import DBPool
from app.core.dependencies import get_model_client
from app.core.exceptions import SessionExpiredError
from app.services import session_service
from app.services.caption_model_service import CaptionModelService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws/sessions", tags=["sessions"])


async def _wait_for_chunk_or_expiry(
    websocket: WebSocket,
    expires_at: datetime,
    inactivity_timeout: float,
) -> bytes:
    timeout = (expires_at - datetime.now(timezone.utc)).total_seconds()
    if timeout <= 0:
        raise SessionExpiredError()

    effective_timeout = min(timeout, inactivity_timeout)

    try:
        return await asyncio.wait_for(
            websocket.receive_bytes(),
            timeout=effective_timeout,
        )
    except asyncio.TimeoutError:
        if datetime.now(timezone.utc) >= expires_at:
            raise SessionExpiredError()
        raise


@router.websocket("/{session_id}/stream")
async def stream_audio(
    websocket: WebSocket,
    session_id: UUID,
    db: DBPool,
    supabase: AsyncClient = Depends(get_supabase_client),
    model_client: ModelClient = Depends(get_model_client),
):
    await websocket.accept()

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    try:
        user_id = verify_jwt(token)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid token")
        return

    session = await session_service.get_session(
        db=db,
        session_id=session_id,
        user_id=user_id,
    )
    if not session or not session.is_active:
        await websocket.close(code=1008, reason="Session not found or inactive")
        return

    settings = get_settings()
    caption_model_service = CaptionModelService(model_client)
    transcript_chunks: list[str] = []
    chunk_index = 0
    disconnected = False
    close_code = 1000
    close_reason = "Session ended"
    send_inactivity_message = False
    send_expiry_message = False

    try:
        await caption_model_service.start_session(session)
        await caption_model_service.upload_notes(
            session=session,
            db=db,
            supabase=supabase,
        )

        while True:
            chunk = await _wait_for_chunk_or_expiry(
                websocket=websocket,
                expires_at=session.expires_at,
                inactivity_timeout=settings.SESSION_TIMEOUT_SECONDS,
            )
            result = await caption_model_service.transcribe(
                session=session,
                audio_chunk=chunk,
                chunk_index=chunk_index,
            )
            chunk_index += 1
            transcript_chunks.append(result)

            await session_service.slide_expiry(db=db, session_id=session_id)
            await websocket.send_json({"type": "caption", "text": result})
    except SessionExpiredError:
        close_code = 4001
        close_reason = "Session expired"
        send_expiry_message = True
    except asyncio.TimeoutError:
        close_code = 4000
        close_reason = "Session timed out"
        send_inactivity_message = True
    except WebSocketDisconnect:
        disconnected = True
    except Exception:
        logger.exception("Unexpected error in stream_audio")
        close_code = 1011
        close_reason = "Internal server error"
    finally:
        if send_expiry_message:
            try:
                await websocket.send_json({"type": "error", "text": "Session expired"})
            except Exception:
                pass

        if send_inactivity_message:
            try:
                await websocket.send_json(
                    {"type": "error", "text": "Session timed out due to inactivity"}
                )
            except Exception:
                pass

        try:
            transcript = await caption_model_service.finalize(
                session=session,
                transcript_chunks=transcript_chunks,
                db=db,
                supabase=supabase,
            )
            if not disconnected:
                try:
                    await websocket.send_json({"type": "final", "text": transcript})
                except Exception:
                    pass
        except Exception:
            logger.exception(
                "Failed to finalize model transcript for session %s", session_id
            )

        try:
            await caption_model_service.end_session_and_cleanup(
                session=session,
                db=db,
                supabase=supabase,
            )
        except Exception:
            logger.exception("Failed to end and cleanup session %s", session_id)

        if not disconnected:
            try:
                await websocket.close(code=close_code, reason=close_reason)
            except Exception:
                pass
