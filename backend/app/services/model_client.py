import httpx

from app.core.config import get_settings


class ModelClient:
    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(
            base_url=self.settings.MODEL_BASE_URL,
            headers={"Authorization": f"Bearer {self.settings.MODEL_API_KEY}"},
        )

    async def health_check(self) -> bool:
        resp = await self.client.get("/v1/health")
        return resp.status_code == 200

    async def transcribe_chunk(self, session_id: str, audio: bytes) -> dict:
        resp = await self.client.post(
            "/v1/transcribe-chunk",
            data={"session_id": session_id},
            files={"audio": ("chunk.wav", audio, "audio/wav")},
        )
        return resp.json()
