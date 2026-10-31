from typing import Sequence
from uuid import UUID
import httpx

from app.clients.caption_model_client import ModelClient
from app.core.exceptions import ProviderRequestError
from app.ports.captioning import ProviderCapabilities


class CustomModelProvider:
    capabilities = ProviderCapabilities(name="custom", supports_pdf_notes=True)

    def __init__(self, client: ModelClient):
        self._client = client

    async def start_session(self, session_id: UUID, mode: str) -> None:
        await self._client.init_session(session_id, mode)

    async def process_notes(self, session_id: UUID, pdf_bytes: bytes) -> None:
        await self._client.process_notes(session_id, pdf_bytes)

    async def transcribe(self, session_id: UUID, audio: bytes, chunk_index: int, mode: str) -> str:
        try:
            return (await self._client.transcribe_chunk(session_id, audio, chunk_index, mode)).partial_text
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise ProviderRequestError(f"Model server returned HTTP {status}", retryable=status >= 500) from exc
        except httpx.TransportError as exc:
            raise ProviderRequestError("Model server request failed", retryable=True) from exc

    async def finalize(self, session_id: UUID, transcript_chunks: Sequence[str]) -> str:
        return (await self._client.finalize(session_id)).final_transcript
