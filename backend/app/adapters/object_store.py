"""Supabase Storage implementation; SDK-specific options stay here."""
from typing import Sequence

from supabase import AsyncClient


class SupabaseObjectStore:
    def __init__(self, client: AsyncClient):
        self._client = client

    async def put(self, bucket: str, key: str, data: bytes, *, content_type: str) -> None:
        await self._client.storage.from_(bucket).upload(
            key, data, {"content-type": content_type, "upsert": "true"}
        )

    async def get(self, bucket: str, key: str) -> bytes:
        return await self._client.storage.from_(bucket).download(key)

    async def delete(self, bucket: str, keys: Sequence[str]) -> None:
        if keys:
            await self._client.storage.from_(bucket).remove(list(keys))

    async def ensure_bucket(self, bucket: str) -> None:
        try:
            await self._client.storage.get_bucket(bucket)
            return
        except Exception:
            pass
        try:
            await self._client.storage.create_bucket(bucket, options={"public": False})
        except Exception:
            # A concurrent request may have created it; verify before continuing.
            await self._client.storage.get_bucket(bucket)
