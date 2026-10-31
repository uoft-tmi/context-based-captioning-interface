from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.clients import pool


async def test_pool_reopens_after_shutdown_and_bounds_commands():
    connection_pool = SimpleNamespace(close=AsyncMock())
    with patch.object(pool.asyncpg, 'create_pool', new=AsyncMock(return_value=connection_pool)) as create:
        await pool.create_pool('postgresql://test')
        assert pool.get_pool() is connection_pool
        assert create.call_args.kwargs['statement_cache_size'] == 0
        assert create.call_args.kwargs['command_timeout'] > 0
        await pool.close_pool()
        with pytest.raises(RuntimeError, match='not initialised'):
            pool.get_pool()
        await pool.create_pool('postgresql://test')
        assert create.await_count == 2
        await pool.close_pool()
