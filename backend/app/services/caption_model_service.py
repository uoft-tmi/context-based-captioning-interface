import logging

from app.core.exceptions import ModelUnavailableError
from app.models.session import Session
from app.utils.pdf_helper import format_transcript
from app.ports.captioning import CaptionStore, TranscriptionProvider

logger = logging.getLogger(__name__)


class CaptionModelService:
    """Caption orchestration depends on application ports, not HTTP/SQL/storage SDKs."""

    def __init__(self, provider: TranscriptionProvider, store: CaptionStore):
        self._provider = provider
        self._store = store

    async def start_session(self, session: Session) -> None:
        if session.mode == "context" and not self._provider.capabilities.supports_pdf_notes:
            raise ValueError("This transcription provider supports baseline sessions only")
        await self._provider.start_session(session.id, session.mode)

    async def upload_notes(self, session: Session) -> None:
        if session.mode != "context":
            return
        notes = await self._store.load_notes(session)
        if not notes:
            raise ValueError("Upload at least one PDF before recording with lecture notes, or create an audio-only session.")
        for pdf in notes:
            await self._provider.process_notes(session.id, pdf)

    async def transcribe(self, session: Session, audio_chunk: bytes, chunk_index: int) -> str:
        return await self._provider.transcribe(session.id, audio_chunk, chunk_index, session.mode)

    async def finalize(self, session: Session, transcript_chunks: list[str]) -> str:
        try:
            transcript = await self._provider.finalize(session.id, transcript_chunks)
        except ModelUnavailableError:
            logger.warning("Model unavailable at finalization; preserving received captions for session %s", session.id)
            transcript = " ".join(transcript_chunks)
        transcript = format_transcript(transcript)
        await self._store.save_transcript(session, transcript)
        return transcript

    async def cleanup_notes(self, session: Session) -> None:
        await self._store.cleanup_notes(session)
