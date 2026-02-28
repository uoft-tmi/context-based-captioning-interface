import uuid

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from pydantic import BaseModel

from middleware.auth import get_current_user_id

router = APIRouter()


# ---------- Request / Response schemas ----------

class CreateSessionRequest(BaseModel):
    mode: str  # "baseline" or "context"


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str


class ChunkRequest(BaseModel):
    chunk_index: int
    audio_b64: str
    mime: str = "audio/wav"


class ChunkResponse(BaseModel):
    partial_text: str


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    mode: str
    transcript_preview: str | None = None


class StopResponse(BaseModel):
    session_id: str
    status: str
    transcript: str | None = None


# ---------- Routes ----------

@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    body: CreateSessionRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Create a new captioning session (baseline or context mode)."""
    session_id = str(uuid.uuid4())
    return CreateSessionResponse(session_id=session_id, status="init")


@router.post("/sessions/{session_id}/notes")
async def upload_notes(
    session_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    """Upload PDF notes for context mode."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit")
    return {"session_id": session_id, "status": "notes_processing"}


@router.post("/sessions/{session_id}/start")
async def start_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Explicitly start a session (optional — session also starts on first chunk)."""
    return {"session_id": session_id, "status": "streaming"}


@router.post("/sessions/{session_id}/chunks", response_model=ChunkResponse)
async def send_chunk(
    session_id: str,
    body: ChunkRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Send an audio chunk for transcription."""
    return ChunkResponse(partial_text=f"[stub] transcription for chunk {body.chunk_index}")


@router.post("/sessions/{session_id}/stop", response_model=StopResponse)
async def stop_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Finalize session and return transcript."""
    return StopResponse(
        session_id=session_id,
        status="complete",
        transcript="[stub] Full transcript text would appear here.",
    )


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get session status and optional transcript preview."""
    return SessionStatusResponse(
        session_id=session_id,
        status="init",
        mode="baseline",
    )


@router.get("/sessions/{session_id}/download")
async def download_transcript(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Download the final transcript file."""
    return {"session_id": session_id, "download_url": None, "message": "[stub] transcript download"}
