import asyncio
from typing import Optional

import asyncpg
from app.core.config import get_settings


_pool: Optional[asyncpg.Pool] = None


async def create_pool(dsn: str) -> None:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            dsn,
            min_size=settings.DB_POOL_MIN_SIZE,
            max_size=settings.DB_POOL_MAX_SIZE,
            command_timeout=settings.DB_COMMAND_TIMEOUT_SECONDS,
            timeout=settings.DB_ACQUIRE_TIMEOUT_SECONDS,
            statement_cache_size=0,
        )


async def close_pool() -> None:
    global _pool
    pool, _pool = _pool, None
    if pool is not None:
        try:
            await asyncio.wait_for(pool.close(), timeout=10)
        except TimeoutError:
            pool.terminate()


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call create_pool() first")
    return _pool
