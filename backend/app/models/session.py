from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


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
    pdf_url: Optional[str] = None  # where the uploaded PDF is stored
    status: SessionStatus
    created_at: datetime
    expires_at: datetime
    finalized_at: Optional[datetime] = None
    final_transcript: Optional[str] = None


class CreateSessionRequest(BaseModel):
    mode: SessionMode
    expires_at: datetime
    pdf_url: Optional[str] = None
