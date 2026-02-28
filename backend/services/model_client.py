import httpx

from config import settings


class ModelClient:
    """HTTP client for the model server (GPU endpoint)."""

    def __init__(self) -> None:
        self.base_url = settings.model_base_url
        self.headers = {"Authorization": f"Bearer {settings.model_api_key}"}

    async def health(self) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/v1/health", headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def init_session(self, session_id: str, mode: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/init",
                headers=self.headers,
                json={"session_id": session_id, "mode": mode},
            )
            resp.raise_for_status()
            return resp.json()

    async def process_notes(self, session_id: str, pdf_bytes: bytes) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/process-notes",
                headers=self.headers,
                files={"file": ("notes.pdf", pdf_bytes, "application/pdf")},
                data={"session_id": session_id},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def transcribe_chunk(
        self, session_id: str, chunk_index: int, audio_b64: str, mode: str
    ) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/transcribe-chunk",
                headers=self.headers,
                json={
                    "session_id": session_id,
                    "chunk_index": chunk_index,
                    "audio_b64": audio_b64,
                    "mode": mode,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def finalize(self, session_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/finalize",
                headers=self.headers,
                json={"session_id": session_id},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()


model_client = ModelClient()
