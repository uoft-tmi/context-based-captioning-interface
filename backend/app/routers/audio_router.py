import asyncio
import base64
import binascii
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.core.auth import get_token_verifier
from app.core.config import get_settings
from app.core.dependencies import get_caption_service, get_stream_sessions
from app.core.exceptions import DemoAccessDenied, ModelUnavailableError, ProviderRequestError, SessionExpiredError
from app.services.caption_model_service import CaptionModelService
from app.utils.audio_helper import bounded_wav
from app.ports.captioning import StreamSessionRepository, TokenVerifier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws/sessions", tags=["sessions"])


async def _safe_send_json(websocket: WebSocket, payload: dict) -> bool:
    try:
        await websocket.send_json(payload)
        return True
    except (RuntimeError, WebSocketDisconnect, OSError):
        return False


async def _safe_close(websocket: WebSocket, *, code: int, reason: str) -> None:
    try:
        await websocket.close(code=code, reason=reason)
    except (RuntimeError, WebSocketDisconnect, OSError):
        pass


@dataclass
class AudioChunk:
    audio: bytes
    index: int | None = None


def _decode_audio_payload_from_text(text: str) -> AudioChunk | None:
    limit = get_settings().MAX_AUDIO_CHUNK_BYTES
    if len(text) > ((limit + 2) // 3) * 4 + 4096:
        raise ValueError("Audio chunk is too large")
    value = text.strip()
    index = None
    if value.startswith("{"):
        payload = json.loads(value)
        if payload.get("type") == "stop":
            return None
        index = payload.get("chunk_index")
        if index is not None and (type(index) is not int or index < 0):
            raise ValueError("Invalid chunk_index")
        value = payload.get("audio_b64") or payload.get("audioB64")
    if not isinstance(value, str) or not value:
        raise ValueError("Missing audio_b64 field")
    try:
        audio = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid base64 audio") from exc
    if not audio or len(audio) > limit:
        raise ValueError("Audio chunk is empty or too large")
    return AudioChunk(audio, index)


async def _wait_for_chunk_or_expiry(websocket: WebSocket, expires_at: datetime, inactivity_timeout: float) -> AudioChunk | None:
    remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        raise SessionExpiredError()
    try:
        message = await asyncio.wait_for(websocket.receive(), timeout=min(remaining, inactivity_timeout))
    except TimeoutError:
        if datetime.now(timezone.utc) >= expires_at:
            raise SessionExpiredError()
        raise
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(code=message.get("code", 1000))
    audio = message.get("bytes")
    if audio is not None:
        if not audio or len(audio) > get_settings().MAX_AUDIO_CHUNK_BYTES:
            raise ValueError("Audio chunk is empty or too large")
        return AudioChunk(audio)
    if isinstance(message.get("text"), str):
        return _decode_audio_payload_from_text(message["text"])
    raise ValueError("Missing audio payload")


@router.websocket("/{session_id}/stream")
async def stream_audio(
    websocket: WebSocket,
    session_id: UUID,
    sessions: StreamSessionRepository = Depends(get_stream_sessions),
    service: CaptionModelService = Depends(get_caption_service),
    verifier: TokenVerifier = Depends(get_token_verifier),
):
    await websocket.accept()
    stream_id = uuid4()
    claimed = False
    model_started = False
    disconnected = False
    error = None
    close_code = 1000
    transcript_chunks: list[str] = []
    settings = get_settings()
    session = None
    try:
        token = websocket.query_params.get("token") or websocket.query_params.get("access_token")
        if not token:
            raise HTTPException(401, "Missing token")
        try:
            # JWKS retrieval is synchronous; keep it off the streaming event loop.
            user_id = await run_in_threadpool(verifier.verify, token)
        except DemoAccessDenied as exc:
            raise HTTPException(403, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(401, "Invalid token") from exc
        session = await sessions.get(session_id, user_id)
        if session is None:
            raise HTTPException(404, "Session not found")
        if not session.is_active or session.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(410, "Session ended or expired")
        session = await sessions.claim(session_id, user_id, stream_id)
        if session is None:
            raise HTTPException(409, "Session already streaming, ended or expired")
        claimed = True
        async with asyncio.timeout(settings.STREAM_SETUP_TIMEOUT_SECONDS):
            await service.start_session(session)
            model_started = True
            await service.upload_notes(session)
        if not await sessions.refresh(session_id, stream_id):
            raise SessionExpiredError()
        await websocket.send_json({"type": "ready", "session_id": str(session_id), "recording_limit_seconds": session.recording_limit_seconds})

        # Allow the last buffered segment to arrive after capture stops; decoded
        # audio duration is independently capped and committed for every chunk.
        recording_deadline = min(session.expires_at, datetime.now(timezone.utc) + timedelta(seconds=session.recording_limit_seconds + settings.CHUNK_TIMEOUT_SECONDS))
        chunk_index = 0
        while True:
            chunk = await _wait_for_chunk_or_expiry(websocket, recording_deadline, settings.SESSION_TIMEOUT_SECONDS)
            if chunk is None:
                break
            started = perf_counter()
            if chunk.index is not None and chunk.index != chunk_index:
                raise ValueError(f"Expected chunk_index {chunk_index}, received {chunk.index}")
            if not await sessions.refresh(session_id, stream_id):
                raise SessionExpiredError()
            remaining_ms = session.recording_limit_seconds * 1000 - session.recorded_duration_ms
            accepted_audio, duration_ms = bounded_wav(chunk.audio, remaining_ms)
            if not duration_ms:
                break
            if not await sessions.record_audio(session_id, stream_id, duration_ms):
                raise SessionExpiredError()
            session.recorded_duration_ms += duration_ms
            current_index = chunk_index
            chunk_index += 1
            try:
                async with asyncio.timeout(settings.CHUNK_TIMEOUT_SECONDS):
                    text = await service.transcribe(session, accepted_audio, current_index)
            except (TimeoutError, ModelUnavailableError) as exc:
                if isinstance(exc, ProviderRequestError) and not exc.retryable:
                    raise
                logger.warning("Chunk transcription failed session_id=%s chunk_index=%d", session_id, current_index, exc_info=True)
                await websocket.send_json({"type": "warning", "text": "Audio chunk could not be transcribed. Continuing with the next chunk.", "chunk_index": current_index})
                if session.recorded_duration_ms >= session.recording_limit_seconds * 1000:
                    break
                continue
            transcript_chunks.append(text)
            latency_ms = (perf_counter() - started) * 1000
            await websocket.send_json({"type": "caption", "text": text, "partial_text": text, "chunk_index": current_index, "latency_ms": round(latency_ms, 2)})
            logger.info("chunk_transcribed session_id=%s chunk_index=%d latency_ms=%.2f", session_id, current_index, latency_ms)
            if session.recorded_duration_ms >= session.recording_limit_seconds * 1000:
                break
    except WebSocketDisconnect:
        disconnected = True
    except SessionExpiredError:
        await _safe_send_json(websocket, {"type": "warning", "text": "Session ended or reached its duration limit."})
    except HTTPException as exc:
        error = str(exc.detail)
        close_code = 1008
    except ProviderRequestError as exc:
        error = str(exc)
        close_code = 1011
    except ValueError as exc:
        error = str(exc)
        close_code = 1003
    except TimeoutError:
        error = "Session setup or inactivity timeout"
        close_code = 4000
    except Exception:
        logger.exception("Streaming failed session_id=%s", session_id)
        error = "Streaming service failed"
        close_code = 1011
    finally:
        transcript = None
        if model_started:
            try:
                # Preserve ownership throughout slow finalization, including a hard-limit stop.
                if not await sessions.refresh(session_id, stream_id, require_active=False):
                    raise RuntimeError("Stream lease no longer owned")
                async with asyncio.timeout(settings.STREAM_FINALIZE_TIMEOUT_SECONDS):
                    transcript = await service.finalize(session, transcript_chunks)
            except Exception:
                logger.exception("Transcript persistence failed session_id=%s", session_id)
                error = error or "Unable to save the final transcript"
                close_code = 1011
        if claimed:
            try:
                finished = await sessions.finish(session_id, stream_id, error)
                if not finished:
                    raise RuntimeError("Stream lease no longer owned")
                await service.cleanup_notes(session)
            except Exception:
                logger.exception("Stream cleanup failed session_id=%s", session_id)
                error = error or "Unable to finish the session"
                close_code = 1011
        if not disconnected:
            if error:
                await _safe_send_json(websocket, {"type": "error", "text": error})
            elif transcript is not None:
                # Completion acknowledges durable storage and the PostgreSQL commit.
                await _safe_send_json(websocket, {"type": "final", "text": transcript, "done": True, "transcript_saved": True})
            await _safe_close(websocket, code=close_code, reason="Session ended" if not error else "Stream failed")
