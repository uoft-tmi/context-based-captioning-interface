from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, HttpUrl, Field, field_validator


class SessionMode(str, Enum):
    context = "context"  # context based captioning
    baseline = "baseline"  # no context based captioning


class Session(BaseModel):
    id: UUID
    user_id: UUID
    mode: SessionMode
    name: str = "Untitled session"
    recording_limit_seconds: int = 30
    recorded_duration_ms: int = 0
    recording_started_at: Optional[datetime] = None
    deleting_at: Optional[datetime] = None
    transcript_text: Optional[str] = None
    has_transcript: bool = False
    is_recording: bool = False
    is_active: bool
    error: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    finalized_at: Optional[datetime] = None
    transcript_key: Optional[str] = None


class CreateSessionRequest(BaseModel):
    mode: SessionMode
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        if isinstance(value, str):
            return " ".join(value.split())
        return value


class AccountOverview(BaseModel):
    plan: str
    recording_limit_seconds: int


class LibraryFile(BaseModel):
    id: UUID
    session_id: UUID
    session_name: str
    filename: str
    created_at: datetime


class UploadLinkResponse(BaseModel):
    bucket: str
    object_path: str
    token: str
    signed_url: HttpUrl
    expires_in: int  # seconds


class SessionErrorRequest(BaseModel):
    reason: str
    details: Optional[str] = None
    source: Optional[str] = None
