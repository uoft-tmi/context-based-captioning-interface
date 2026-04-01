from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class SessionMode(str, Enum):
    context = "context"  # context based captioning
    baseline = "baseline"  # no context based captioning


class Session(BaseModel):
    id: UUID
    user_id: UUID
    mode: SessionMode
    is_active: bool
    error: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    finalized_at: Optional[datetime] = None
    transcript_key: Optional[str] = None


class CreateSessionRequest(BaseModel):
    mode: SessionMode


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
