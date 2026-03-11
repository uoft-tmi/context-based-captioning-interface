from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class SessionMode(str, Enum):
    baseline = "baseline"
    context = "context"


# ── Session ──────────────────────────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    mode: SessionMode


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str = "init"


# ── Notes ────────────────────────────────────────────────────────────────────


class NotesResponse(BaseModel):
    status: str = "processed"


# ── Chunks ───────────────────────────────────────────────────────────────────


class SendChunkRequest(BaseModel):
    chunk_index: int = Field(..., ge=0)
    audio_b64: str
    mime: Literal["audio/wav"] = "audio/wav"


class SendChunkResponse(BaseModel):
    partial_text: str


# ── Stop / Finalize ───────────────────────────────────────────────────────────


class StopSessionResponse(BaseModel):
    final_transcript: str
    download_url: str


# ── Error ────────────────────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    detail: str
