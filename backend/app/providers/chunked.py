"""Stateless providers that transcribe individual WAV chunks."""
import asyncio
import base64
from typing import Sequence
from uuid import UUID

import httpx

from app.core.exceptions import ProviderRequestError
from app.ports.captioning import ProviderCapabilities


class BaselineChunkProvider:
    capabilities: ProviderCapabilities

    async def start_session(self, session_id: UUID, mode: str) -> None:
        if mode != "baseline":
            raise ValueError("This provider supports audio-only baseline sessions")

    async def process_notes(self, session_id: UUID, pdf_bytes: bytes) -> None:
        raise ValueError("This provider does not accept PDF notes")

    async def finalize(self, session_id: UUID, transcript_chunks: Sequence[str]) -> str:
        # These APIs have no remote session or finalize endpoint to call.
        return " ".join(transcript_chunks)


class HostedChunkProvider(BaselineChunkProvider):
    def __init__(self, client: httpx.AsyncClient, api_key: str, base_url: str,
                 language: str, timeout_seconds: float):
        if not api_key.strip():
            raise ValueError(f"Missing API key for {self.capabilities.name}")
        self._client = client
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._language = language
        self._timeout = timeout_seconds

    async def _request(self, path: str, **kwargs) -> str:
        name = self.capabilities.name
        try:
            response = await self._client.post(
                self._base_url + path,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._timeout,
                **kwargs,
            )
        except httpx.TransportError as exc:
            raise ProviderRequestError(f"{name} transcription request failed", retryable=True) from exc
        if response.status_code == 429:
            raise ProviderRequestError(f"{name} rate limit reached. Wait before retrying; use the mock provider for concurrent load tests.")
        if response.status_code in (401, 403):
            raise ProviderRequestError(f"{name} authentication failed. Check the backend API key and account access.")
        if response.is_error:
            raise ProviderRequestError(f"{name} returned HTTP {response.status_code}", retryable=response.status_code >= 500)
        try:
            data = response.json()
            text = data["text"]
            if not isinstance(text, str):
                raise ValueError("text is not a string")
            return text
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderRequestError(f"{name} returned an invalid transcription response") from exc


class GroqWhisperProvider(HostedChunkProvider):
    # Start with one second for a quicker first caption, then ~19 calls/minute.
    # Leave room for a final partial chunk under the 20 RPM free-tier limit.
    # Quotas are organization-wide; other recordings/apps still share them.
    capabilities = ProviderCapabilities(
        name="groq", supports_pdf_notes=False,
        recommended_chunk_ms=3200, initial_chunk_ms=1000,
        min_request_interval_ms=3200,
    )

    def __init__(self, client: httpx.AsyncClient, api_key: str, *,
                 base_url: str = "https://api.groq.com/openai/v1",
                 model: str = "whisper-large-v3-turbo", language: str = "en",
                 timeout_seconds: float = 15):
        super().__init__(client, api_key, base_url, language, timeout_seconds)
        self._model = model

    async def transcribe(self, session_id: UUID, audio: bytes, chunk_index: int, mode: str) -> str:
        data = {"model": self._model, "response_format": "json"}
        if self._language:
            data["language"] = self._language
        return await self._request("/audio/transcriptions", data=data,
                                   files={"file": (f"chunk-{chunk_index}.wav", audio, "audio/wav")})


class WisprFlowProvider(HostedChunkProvider):
    """Official API-key REST endpoint. Requires approved Wispr API access."""
    capabilities = ProviderCapabilities(name="wispr", supports_pdf_notes=False)

    def __init__(self, client: httpx.AsyncClient, api_key: str, *,
                 base_url: str = "https://platform-api.wisprflow.ai/api/v1/dash",
                 language: str = "en", timeout_seconds: float = 15):
        super().__init__(client, api_key, base_url, language, timeout_seconds)

    async def transcribe(self, session_id: UUID, audio: bytes, chunk_index: int, mode: str) -> str:
        body = {"audio": base64.b64encode(audio).decode(),
                "context": {"app": {"name": "Lecture Captioning", "type": "other"}}}
        if self._language:
            body["language"] = [self._language]
        return await self._request("/api", json=body)


class MockTranscriptionProvider(BaselineChunkProvider):
    """Synthetic text for deterministic tests; does not recognize speech."""
    capabilities = ProviderCapabilities(name="mock", supports_pdf_notes=False)

    def __init__(self, *, delay_ms: float = 20, text: str = "Test caption"):
        self._delay_ms = delay_ms
        self._text = text

    async def transcribe(self, session_id: UUID, audio: bytes, chunk_index: int, mode: str) -> str:
        await asyncio.sleep(self._delay_ms / 1000)
        return f"{self._text} {chunk_index}"
