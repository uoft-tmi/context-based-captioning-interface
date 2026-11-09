import io
import wave
from dataclasses import replace
from typing import Sequence
from uuid import UUID

from app.core.config import Settings
from app.core.exceptions import ProviderRequestError
from app.ports.captioning import TranscriptionProvider
from app.ports.usage import TranscriptionBudget


class BudgetedTranscriptionProvider:
    def __init__(self, provider: TranscriptionProvider, budget: TranscriptionBudget, settings: Settings):
        self._provider, self._budget, self._settings = provider, budget, settings
        interval = settings.PROVIDER_MIN_CHUNK_INTERVAL_MS + 200
        self.capabilities = replace(provider.capabilities,
            min_request_interval_ms=max(provider.capabilities.min_request_interval_ms, interval),
            recommended_chunk_ms=max(provider.capabilities.recommended_chunk_ms, interval))

    async def start_session(self, session_id: UUID, mode: str) -> None:
        if not self._settings.TRANSCRIPTION_ENABLED:
            raise ProviderRequestError("Transcription is temporarily disabled by the administrator.")
        if self.capabilities.name == 'custom':
            await self._budget.reserve(session_id, 'start')
        await self._provider.start_session(session_id, mode)

    async def process_notes(self, session_id: UUID, pdf_bytes: bytes) -> None:
        if not self._settings.TRANSCRIPTION_ENABLED:
            raise ProviderRequestError("Transcription is temporarily disabled by the administrator.")
        if self.capabilities.name == 'custom':
            await self._budget.reserve(session_id, 'notes')
        await self._provider.process_notes(session_id, pdf_bytes)

    async def transcribe(self, session_id: UUID, audio: bytes, chunk_index: int, mode: str) -> str:
        if self.capabilities.name != 'mock':
            with wave.open(io.BytesIO(audio), 'rb') as source:
                duration_ms = (source.getnframes() * 1000 + source.getframerate() - 1) // source.getframerate()
            await self._budget.reserve(session_id, 'transcribe', duration_ms)
        elif not self._settings.TRANSCRIPTION_ENABLED:
            raise ProviderRequestError("Transcription is temporarily disabled by the administrator.")
        return await self._provider.transcribe(session_id, audio, chunk_index, mode)

    async def finalize(self, session_id: UUID, transcript_chunks: Sequence[str]) -> str:
        if self.capabilities.name == 'custom':
            await self._budget.reserve(session_id, 'finalize')
        return await self._provider.finalize(session_id, transcript_chunks)
