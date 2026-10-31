"""Application-owned contracts. Vendor clients and SQL belong in adapters."""
from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable
from uuid import UUID

from app.models.session import Session


@dataclass(frozen=True)
class ProviderCapabilities:
    name: str
    supports_pdf_notes: bool
    recommended_chunk_ms: int = 2500
    initial_chunk_ms: int | None = None
    min_request_interval_ms: int = 0


@runtime_checkable
class TranscriptionProvider(Protocol):
    capabilities: ProviderCapabilities

    async def start_session(self, session_id: UUID, mode: str) -> None: ...
    async def process_notes(self, session_id: UUID, pdf_bytes: bytes) -> None: ...
    async def transcribe(self, session_id: UUID, audio: bytes, chunk_index: int, mode: str) -> str: ...
    async def finalize(self, session_id: UUID, transcript_chunks: Sequence[str]) -> str: ...


@runtime_checkable
class CaptionStore(Protocol):
    async def load_notes(self, session: Session) -> list[bytes]: ...
    async def save_transcript(self, session: Session, transcript: str) -> None: ...
    async def cleanup_notes(self, session: Session) -> None: ...


@runtime_checkable
class StreamSessionRepository(Protocol):
    async def record_audio(self, session_id: UUID, stream_id: UUID, duration_ms: int) -> bool: ...
    async def get(self, session_id: UUID, user_id: UUID) -> Session | None: ...
    async def claim(self, session_id: UUID, user_id: UUID, stream_id: UUID) -> Session | None: ...
    async def refresh(self, session_id: UUID, stream_id: UUID, *, require_active: bool = True) -> bool: ...
    async def finish(self, session_id: UUID, stream_id: UUID, error: str | None = None) -> bool: ...


@runtime_checkable
class TokenVerifier(Protocol):
    def verify(self, token: str) -> UUID: ...
