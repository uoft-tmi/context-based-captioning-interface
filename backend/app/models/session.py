from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class SessionMode(str, Enum):
    context = "context"  # context based captioning
    baseline = "baseline"  # no context based captioning


class SessionStatus(str, Enum):
    active = "active"
    finalized = "finalized"
    expired = "error"


class Session(BaseModel):
    id: UUID
    user_id: UUID
    mode: SessionMode
    status: SessionStatus
    created_at: datetime
    expires_at: datetime
    finalized_at: Optional[datetime] = None
    final_transcript: Optional[str] = None


class CreateSessionRequest(BaseModel):
    mode: SessionMode


class UploadLinkResponse(BaseModel):
    bucket: str
    object_path: str
    token: str
    signed_url: HttpUrl
    expires_in: int  # seconds
