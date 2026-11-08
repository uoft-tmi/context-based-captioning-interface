from typing import Protocol
from uuid import UUID


class TranscriptionBudget(Protocol):
    async def reserve(self, session_id: UUID, action: str, audio_ms: int = 0) -> None:
        """Reserve before a provider call; raise ProviderRequestError if denied."""
        ...
