import asyncio
from uuid import uuid4

import pytest
import httpx
from websockets.asyncio.client import connect

from app.adapters.usage import PostgresTranscriptionBudget
from app.core.config import Settings, get_settings
from app.core.exceptions import ProviderRequestError
from app.database import sessions_db
from app.providers.guarded import BudgetedTranscriptionProvider
from tests.helpers import wav_audio

pytestmark = pytest.mark.integration


async def recording(db, user=None):
    user = user or uuid4()
    await db.execute('INSERT INTO auth.users(id) VALUES($1) ON CONFLICT DO NOTHING', user)
    session = await sessions_db.create_session(db, user, 'baseline', uuid4().hex)
    stream_id = uuid4()
    await sessions_db.claim_stream(db, session.id, user, stream_id)
    return session, stream_id


def config(**kwargs):
    return Settings(_env_file=None, PROVIDER_MIN_CHUNK_INTERVAL_MS=0, **kwargs)


async def test_concurrent_workers_cannot_overspend_daily_budget(database):
    session, _ = await recording(database)
    # Separate adapters model separate workers sharing the same database.
    settings = config(PROVIDER_REQUESTS_PER_DAY=5)
    workers = [PostgresTranscriptionBudget(database, settings) for _ in range(12)]
    results = await asyncio.gather(*(worker.reserve(session.id, 'transcribe', 1000) for worker in workers), return_exceptions=True)
    assert sum(result is None for result in results) == 5
    assert sum(isinstance(result, ProviderRequestError) for result in results) == 7
    assert await database.fetchval('SELECT COUNT(*) FROM provider_usage') == 5


async def test_deleting_sessions_and_restarting_adapter_do_not_reset_usage(database):
    session, stream_id = await recording(database)
    settings = config(PROVIDER_REQUESTS_PER_USER_PER_DAY=1)
    await PostgresTranscriptionBudget(database, settings).reserve(session.id, 'transcribe', 1000)
    await sessions_db.finish_stream(database, session.id, stream_id)
    await sessions_db.begin_delete(database, session.id, session.user_id)
    await sessions_db.delete_session(database, session.id, session.user_id)
    next_session, _ = await recording(database, session.user_id)
    with pytest.raises(ProviderRequestError, match='daily demo request'):
        await PostgresTranscriptionBudget(database, settings).reserve(next_session.id, 'transcribe', 1000)
    assert await database.fetchval('SELECT COUNT(*) FROM provider_usage') == 1


async def test_global_budget_applies_across_accounts(database):
    first, _ = await recording(database)
    second, _ = await recording(database)
    budget = PostgresTranscriptionBudget(database, config(PROVIDER_REQUESTS_PER_DAY=1))
    await budget.reserve(first.id, 'transcribe', 1000)
    with pytest.raises(ProviderRequestError, match='daily demo request'):
        await budget.reserve(second.id, 'transcribe', 1000)


async def test_short_audio_reserves_ten_seconds_and_daily_window_resets(database):
    session, _ = await recording(database)
    budget = PostgresTranscriptionBudget(database, config(PROVIDER_AUDIO_SECONDS_PER_USER_PER_DAY=10))
    await budget.reserve(session.id, 'transcribe', 1)
    assert await database.fetchval('SELECT audio_ms FROM provider_usage') == 10000
    with pytest.raises(ProviderRequestError, match='audio allowance'):
        await budget.reserve(session.id, 'transcribe', 1)
    await database.execute("UPDATE provider_usage SET reserved_at=clock_timestamp()-INTERVAL '1 day'")
    await budget.reserve(session.id, 'transcribe', 1)


async def test_burst_and_shared_minute_limits_are_enforced(database):
    session, _ = await recording(database)
    settings = Settings(_env_file=None, PROVIDER_MIN_CHUNK_INTERVAL_MS=60000)
    await PostgresTranscriptionBudget(database, settings).reserve(session.id, 'transcribe', 1000)
    with pytest.raises(ProviderRequestError, match='too quickly'):
        await PostgresTranscriptionBudget(database, settings).reserve(session.id, 'transcribe', 1000)
    with pytest.raises(ProviderRequestError, match='wait a minute'):
        await PostgresTranscriptionBudget(database, config(PROVIDER_REQUESTS_PER_MINUTE=1)).reserve(session.id, 'start')


async def test_missing_migration_fails_closed(database):
    session, _ = await recording(database)
    await database.execute('DROP TABLE provider_usage')
    with pytest.raises(ProviderRequestError, match='usage checks are unavailable'):
        await PostgresTranscriptionBudget(database, config()).reserve(session.id, 'transcribe', 1000)


async def test_demo_caps_paid_accounts_at_thirty_seconds(database, monkeypatch):
    monkeypatch.setattr(get_settings(), 'DEMO_MODE', True)
    user = uuid4()
    await database.execute("INSERT INTO account_plans(user_id,plan) VALUES($1,'paid')", user)
    session, _ = await recording(database, user)
    assert session.recording_limit_seconds == 30
    assert (await sessions_db.get_session(database, session.id, user)).recording_limit_seconds == 30


async def test_kill_switch_blocks_existing_recordings(database):
    session, _ = await recording(database)
    settings = config()
    budget = PostgresTranscriptionBudget(database, settings)
    await budget.reserve(session.id, 'transcribe', 1000)
    settings.TRANSCRIPTION_ENABLED = False
    with pytest.raises(ProviderRequestError, match='disabled'):
        await budget.reserve(session.id, 'transcribe', 1000)
    assert await database.fetchval('SELECT COUNT(*) FROM provider_usage') == 1


async def test_live_stream_keeps_transcript_when_budget_blocks_custom_finalization(streaming_app, server):
    settings = config(PROVIDER_REQUESTS_PER_DAY=2)
    app = streaming_app.app
    app.state.transcription_provider = BudgetedTranscriptionProvider(app.state.transcription_provider,
        PostgresTranscriptionBudget(streaming_app.db, settings), settings)
    user = uuid4()
    await streaming_app.db.execute('INSERT INTO auth.users(id) VALUES($1)', user)
    async with httpx.AsyncClient() as http:
        response = await http.post(server + '/api/sessions', headers={'Authorization': f'Bearer {user}'}, json={'name': 'Budget demo', 'mode': 'baseline'})
    assert response.status_code == 200
    session_id = response.json()['id']
    async with connect(server.replace('http://', 'ws://') + f'/ws/sessions/{session_id}/stream?access_token={user}') as ws:
        import json
        assert json.loads(await ws.recv())['type'] == 'ready'
        await ws.send(wav_audio(1))
        assert json.loads(await ws.recv())['text'] == 'chunk 0'
        await ws.send(json.dumps({'type': 'stop'}))
        final = json.loads(await ws.recv())
    assert final['transcript_saved'] and final['text'] == 'chunk 0'
    assert await streaming_app.db.fetchval('SELECT COUNT(*) FROM provider_usage') == 2
    assert (await streaming_app.db.fetchrow('SELECT transcript_text FROM sessions'))['transcript_text'] == 'chunk 0'
