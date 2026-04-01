"""supabase client"""

from typing import Optional

from supabase.client import AsyncClient, acreate_client

from app.core.config import get_settings

_settings = get_settings()
_supabase: Optional[AsyncClient] = None


async def init_supabase_client() -> None:
    global _supabase
    _supabase = await acreate_client(
        _settings.SUPABASE_URL, _settings.SUPABASE_SERVICE_KEY
    )


def get_supabase_client() -> AsyncClient:
    if _supabase is None:
        raise RuntimeError(
            "Supabase client not initialized. Call init_supabase_client() first."
        )
    return _supabase
