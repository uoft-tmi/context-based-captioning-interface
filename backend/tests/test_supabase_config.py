from unittest.mock import AsyncMock

import pytest

from app.clients import supabase_client
from app.core.config import Settings


@pytest.fixture(autouse=True)
def clear_supabase_environment(monkeypatch):
    monkeypatch.delenv('SUPABASE_SECRET_KEY', raising=False)


def test_secret_key_configuration():
    settings = Settings(_env_file=None, SUPABASE_SECRET_KEY='sb_secret_test_value')
    assert settings.SUPABASE_SECRET_KEY.get_secret_value() == 'sb_secret_test_value'
    assert 'sb_secret_test_value' not in repr(settings)


async def test_backend_client_uses_secret_key(monkeypatch):
    settings = Settings(_env_file=None, SUPABASE_URL='https://example.supabase.co', SUPABASE_SECRET_KEY='sb_secret_test')
    create = AsyncMock()
    monkeypatch.setattr(supabase_client, 'get_settings', lambda: settings)
    monkeypatch.setattr(supabase_client, 'acreate_client', create)
    monkeypatch.setattr(supabase_client, '_supabase', None)
    await supabase_client.init_supabase_client()
    create.assert_awaited_once_with('https://example.supabase.co', 'sb_secret_test')
    assert supabase_client.get_supabase_client() is create.return_value
