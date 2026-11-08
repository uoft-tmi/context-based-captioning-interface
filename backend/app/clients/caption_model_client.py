import asyncio
from typing import Optional
from uuid import UUID

import httpx
from app.core.config import Settings, get_settings
from app.core.exceptions import ModelUnavailableError
from app.models.caption_model import (
    FinalTranscript,
    HealthResponse,
    InitResponse,
    NotesResponse,
    TranscriptChunk,
)


class ModelClient:
    def __init__(self, client: httpx.AsyncClient, *, settings: Settings | None = None, base_url: str = ""):
        self._client = client
        self._settings = settings or get_settings()
        self._base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return self._base_url + path

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._settings.MODEL_API_KEY}"}

    def _format_http_error(self, exc: httpx.HTTPStatusError) -> str:
        response = exc.response
        status = response.status_code
        reason = response.reason_phrase
        body = ""
        try:
            body = response.text.strip()
        except Exception:
            body = ""
        if body:
            if len(body) > 200:
                body = f"{body[:200]}..."
            return f"{status} {reason}: {body}"
        return f"{status} {reason}"

    async def _post_with_retry(
        self,
        path: str,
        *,
        timeout: float,
        retries: int = 1,
        **kwargs,
    ) -> httpx.Response:
        delay = 1.0
        last_exc: Optional[Exception] = None

        for attempt in range(retries):
            try:
                resp = await self._client.post(
                    self._url(path),
                    headers=self._headers(),
                    timeout=timeout,
                    **kwargs,
                )
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    raise ModelUnavailableError(
                        "Model server auth failed "
                        f"({self._format_http_error(e)}). "
                        "Check MODEL_API_KEY."
                    ) from e
                last_exc = e
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
            except httpx.TransportError as e:
                last_exc = e
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2

        raise ModelUnavailableError("Model server unreachable") from last_exc

    async def health(self) -> HealthResponse:
        resp = await self._client.get(
            self._url("/v1/health"),
            headers=self._headers(),
            timeout=5.0,
        )
        resp.raise_for_status()
        return HealthResponse(**resp.json())

    async def init_session(self, session_id: UUID, mode: str) -> InitResponse:
        resp = await self._post_with_retry(
            "/v1/init",
            json={"session_id": str(session_id), "mode": mode},
            timeout=10.0,
        )
        return InitResponse(**resp.json())

    async def process_notes(self, session_id: UUID, pdf_bytes: bytes) -> NotesResponse:
        resp = await self._post_with_retry(
            "/v1/process-notes",
            files={"pdf_file": ("notes.pdf", pdf_bytes, "application/pdf")},
            data={"session_id": str(session_id)},  # form field
            timeout=self._settings.NOTES_TIMEOUT_SECONDS,
        )
        return NotesResponse(**resp.json())

    async def transcribe_chunk(
        self,
        session_id: UUID,
        audio: bytes,
        chunk_index: int,
        mode: str,
    ) -> TranscriptChunk:
        import base64

        resp = await self._client.post(
            self._url("/v1/transcribe-chunk"),
            json={
                "session_id": str(session_id),
                "chunk_index": chunk_index,
                "audio_b64": base64.b64encode(audio).decode(),
                "mode": mode,
            },
            headers=self._headers(),
            timeout=self._settings.CHUNK_TIMEOUT_SECONDS,
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                raise ModelUnavailableError(
                    "Model server auth failed "
                    f"({self._format_http_error(e)}). "
                    "Check MODEL_API_KEY."
                ) from e
            raise
        return TranscriptChunk(**resp.json())

    async def finalize(self, session_id: UUID) -> FinalTranscript:
        resp = await self._post_with_retry(
            "/v1/finalize",
            json={"session_id": str(session_id)},
            timeout=30.0,
        )
        return FinalTranscript(**resp.json())
