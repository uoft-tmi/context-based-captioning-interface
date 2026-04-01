import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
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


async def _safe_send_json(websocket: WebSocket, payload: dict) -> bool:
    try:
        await websocket.send_json(payload)
        return True
    except Exception:
        return False


async def _safe_close(websocket: WebSocket, *, code: int, reason: str) -> bool:
    try:
        await websocket.close(code=code, reason=reason)
        return True
    except Exception:
        return False


def _decode_audio_payload_from_text(text: str) -> bytes:
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty audio payload")

    # Support frontend JSON payloads like: {"audioB64": "..."}
    if stripped.startswith("{"):
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise ValueError("Invalid audio payload")

        audio_b64 = payload.get("audioB64") or payload.get("audio_b64")
        if not isinstance(audio_b64, str) or not audio_b64:
            raise ValueError("Missing audioB64 field")
        return base64.b64decode(audio_b64)

    # Also support raw base64 text frames.
    return base64.b64decode(stripped)


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
        message = await asyncio.wait_for(websocket.receive(), timeout=effective_timeout)
    except asyncio.TimeoutError:
        if datetime.now(timezone.utc) >= expires_at:
            raise SessionExpiredError()
        raise

    message_type = message.get("type")
    if message_type == "websocket.disconnect":
        raise WebSocketDisconnect(code=message.get("code", 1000))

    if message_type != "websocket.receive":
        raise ValueError("Unexpected websocket message type")

    raw_bytes = message.get("bytes")
    if isinstance(raw_bytes, (bytes, bytearray)):
        return bytes(raw_bytes)

    raw_text = message.get("text")
    if isinstance(raw_text, str):
        return _decode_audio_payload_from_text(raw_text)

    raise ValueError("Missing audio payload")


@router.websocket("/{session_id}/stream")
async def stream_audio(
    websocket: WebSocket,
    session_id: UUID,
    db: DBPool,
    supabase: AsyncClient = Depends(get_supabase_client),
    model_client: ModelClient = Depends(get_model_client),
):
    await websocket.accept()

    token = websocket.query_params.get("token") or websocket.query_params.get(
        "access_token"
    )
    if not token:
        await _safe_send_json(websocket, {"type": "error", "text": "Missing token"})
        await _safe_close(websocket, code=1008, reason="Missing token")
        return

    try:
        user_id = verify_jwt(token)
    except Exception:
        logger.info("Rejected websocket for session %s: invalid token", session_id)
        await _safe_send_json(websocket, {"type": "error", "text": "Invalid token"})
        await _safe_close(websocket, code=1008, reason="Invalid token")
        return

    try:
        session = await session_service.get_session(
            db=db,
            session_id=session_id,
            user_id=user_id,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            await _safe_send_json(
                websocket, {"type": "error", "text": "Session not found"}
            )
            await _safe_close(websocket, code=1008, reason="Session not found")
            return
        logger.warning(
            "Failed loading session %s for websocket user %s: %s",
            session_id,
            user_id,
            exc.detail,
        )
        await _safe_send_json(
            websocket, {"type": "error", "text": "Session lookup failed"}
        )
        await _safe_close(websocket, code=1011, reason="Session lookup failed")
        return

    if not session or not session.is_active:
        await _safe_send_json(
            websocket,
            {"type": "error", "text": "Session not found or inactive"},
        )
        await _safe_close(websocket, code=1008, reason="Session not found or inactive")
        return

    settings = get_settings()
    caption_model_service = CaptionModelService(model_client)
    transcript_chunks: list[str] = []
    chunk_index = 0
    disconnected = False
    model_session_started = False
    close_code = 1000
    close_reason = "Session ended"
    send_inactivity_message = False
    send_expiry_message = False
    send_payload_message = False
    payload_message = "Invalid audio payload"

    try:
        await caption_model_service.start_session(session)
        model_session_started = True
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
    except ValueError as exc:
        close_code = 1003
        close_reason = "Invalid audio payload"
        send_payload_message = True
        payload_message = str(exc)
    except WebSocketDisconnect:
        disconnected = True
    except Exception:
        logger.exception("Unexpected error in stream_audio")
        close_code = 1011
        close_reason = "Internal server error"
    finally:
        # If the client disconnected, keep the session active so it can reconnect
        # without forcing finalize/persist/cleanup on every transient drop.
        if disconnected:
            return

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

        if send_payload_message:
            try:
                await websocket.send_json({"type": "error", "text": payload_message})
            except Exception:
                pass

        if model_session_started and transcript_chunks:
            try:
                transcript = await caption_model_service.finalize(
                    session=session,
                    transcript_chunks=transcript_chunks,
                    db=db,
                    supabase=supabase,
                )
                try:
                    await websocket.send_json({"type": "final", "text": transcript})
                except Exception:
                    pass
            except Exception as exc:
                logger.warning(
                    "Failed to finalize model transcript for session %s: %s",
                    session_id,
                    exc,
                )

        should_end_session = (
            send_expiry_message or send_inactivity_message or close_code == 1011
        )
        if should_end_session:
            try:
                await caption_model_service.end_session_and_cleanup(
                    session=session,
                    db=db,
                    supabase=supabase,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to end and cleanup session %s: %s", session_id, exc
                )

        await _safe_close(websocket, code=close_code, reason=close_reason)
