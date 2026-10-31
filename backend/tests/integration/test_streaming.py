import asyncio
import base64
import io
import json
import os
import wave
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from websockets.asyncio.client import connect

from app.core.config import get_settings
from app.database import sessions_db
from benchmarks.stream_latency import check_budget, run_load

pytestmark = pytest.mark.integration


def wav_chunk():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b'\0\0' * 40000)
    return buffer.getvalue()


async def create_session(app, server, mode='baseline'):
    user_id = uuid4()
    await app.db.execute('INSERT INTO auth.users (id) VALUES ($1)', user_id)
    async with httpx.AsyncClient() as http:
        response = await http.post(server + '/api/sessions', headers={'Authorization': f'Bearer {user_id}'}, json={'mode': mode, 'name': f'Lecture {user_id}'})
    assert response.status_code == 200, response.text
    return user_id, response.json()['id']


def stream_url(server, session_id, user_id):
    return server.replace('http://', 'ws://') + f'/ws/sessions/{session_id}/stream?access_token={user_id}'


@pytest.mark.latency
async def test_concurrent_chunk_to_transcript_p95(streaming_app, server):
    n = int(os.getenv('LATENCY_SESSIONS', '20'))
    users = [uuid4() for _ in range(n)]
    await streaming_app.db.executemany('INSERT INTO auth.users (id) VALUES ($1)', [(user,) for user in users])
    report = await run_load(server, [str(user) for user in users], wav_chunk(),
                            chunks=int(os.getenv('LATENCY_CHUNKS', '10')),
                            interval_ms=float(os.getenv('LATENCY_INTERVAL_MS', '30')))
    print('\nControlled model + real PostgreSQL/WebSocket latency:', json.dumps(report, indent=2))
    check_budget(report, float(os.getenv('LATENCY_P95_MS', '500')))
    rows = await streaming_app.db.fetch('SELECT is_active, stream_id, transcript_key, error FROM sessions')
    assert len(rows) == n
    assert all(not row['is_active'] and row['stream_id'] is None and row['transcript_key'] and row['error'] is None for row in rows)


async def test_stop_persists_before_final_and_download(streaming_app, server):
    user, session_id = await create_session(streaming_app, server)
    async with connect(stream_url(server, session_id, user)) as ws:
        assert json.loads(await ws.recv())['type'] == 'ready'
        for index in range(3):
            await ws.send(json.dumps({'chunk_index': index, 'audio_b64': base64.b64encode(wav_chunk()).decode()}))
            caption = json.loads(await ws.recv())
            assert caption['chunk_index'] == index
            assert caption['text'] == f'chunk {index}'
        await ws.send(json.dumps({'type': 'stop'}))
        final = json.loads(await ws.recv())
        assert final == {'type': 'final', 'text': 'chunk 0 chunk 1 chunk 2', 'done': True, 'transcript_saved': True}
        async with httpx.AsyncClient() as http:
            response = await http.get(server + f'/api/sessions/{session_id}/download', headers={'Authorization': f'Bearer {user}'})
        assert response.status_code == 200
        assert response.content.startswith(b'%PDF')
    session = await sessions_db.get_session(streaming_app.db, UUID(session_id), user)
    assert not session.is_active and session.finalized_at and session.transcript_key


async def test_duplicate_socket_cannot_reset_existing_model(streaming_app, server):
    user, session_id = await create_session(streaming_app, server)
    async with connect(stream_url(server, session_id, user)) as first:
        assert json.loads(await first.recv())['type'] == 'ready'
        async with connect(stream_url(server, session_id, user)) as second:
            assert json.loads(await second.recv())['type'] == 'error'
        async with httpx.AsyncClient() as http:
            response = await http.post(server + f'/api/sessions/{session_id}/end', headers={'Authorization': f'Bearer {user}'})
        assert response.status_code == 409
        await first.send(wav_chunk())
        assert json.loads(await first.recv())['text'] == 'chunk 0'
        await first.send('{"type":"stop"}')
        assert json.loads(await first.recv())['type'] == 'final'


async def test_create_race_keeps_one_active_session(database):
    user = uuid4()
    await database.execute('INSERT INTO auth.users (id) VALUES ($1)', user)
    results = await asyncio.gather(*(sessions_db.create_session(database, user, 'baseline') for _ in range(8)), return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert all(not isinstance(result, Exception) or isinstance(result, asyncpg.UniqueViolationError) for result in results)
    assert await database.fetchval('SELECT count(*) FROM sessions WHERE user_id=$1 AND is_active=TRUE', user) == 1


async def test_expired_session_does_not_block_new_session(database):
    user = uuid4()
    await database.execute('INSERT INTO auth.users (id) VALUES ($1)', user)
    await database.execute("INSERT INTO sessions(user_id,mode,created_at,expires_at) VALUES ($1,'baseline',NOW()-INTERVAL '2 hours',NOW()-INTERVAL '1 hour')", user)
    session = await sessions_db.create_session(database, user, 'baseline')
    assert session.is_active
    assert await database.fetchval('SELECT count(*) FROM sessions WHERE user_id=$1 AND is_active=TRUE', user) == 1


@pytest.mark.parametrize('payload', ['{"audio_b64":"%%%"}', '{"audio_b64":""}', '{"chunk_index":9,"audio_b64":"YQ=="}'])
async def test_bad_audio_does_not_leave_active_session(streaming_app, server, payload):
    user, session_id = await create_session(streaming_app, server)
    async with connect(stream_url(server, session_id, user)) as ws:
        assert json.loads(await ws.recv())['type'] == 'ready'
        await ws.send(payload)
        assert json.loads(await ws.recv())['type'] == 'error'
    assert not await streaming_app.db.fetchval('SELECT is_active FROM sessions WHERE id=$1::uuid', session_id)


async def test_storage_failure_never_reports_success(streaming_app, server):
    user, session_id = await create_session(streaming_app, server)
    streaming_app.storage.fail_upload = True
    async with connect(stream_url(server, session_id, user)) as ws:
        assert json.loads(await ws.recv())['type'] == 'ready'
        await ws.send(wav_chunk())
        assert json.loads(await ws.recv())['type'] == 'caption'
        await ws.send('{"type":"stop"}')
        error = json.loads(await ws.recv())
        assert error['type'] == 'error'
        assert 'save' in error['text']
    row = await streaming_app.db.fetchrow('SELECT is_active,error,transcript_key,transcript_text FROM sessions WHERE id=$1::uuid', session_id)
    assert not row['is_active'] and row['error'] and row['transcript_key'] is None

    assert row['transcript_text'] == 'chunk 0'
    summaries = await sessions_db.get_all_sessions(streaming_app.db, user)
    assert summaries[0].has_transcript and summaries[0].transcript_text is None
    async with httpx.AsyncClient() as http:
        download = await http.get(server + f'/api/sessions/{session_id}/download', headers={'Authorization': f'Bearer {user}'})
        assert download.status_code == 200 and download.content.startswith(b'%PDF')


async def test_temporary_model_failure_allows_next_chunk(streaming_app, server):
    user, session_id = await create_session(streaming_app, server)
    streaming_app.model.fail_chunk = 0
    async with connect(stream_url(server, session_id, user)) as ws:
        assert json.loads(await ws.recv())['type'] == 'ready'
        await ws.send(wav_chunk())
        assert json.loads(await ws.recv())['type'] == 'warning'
        await ws.send(wav_chunk())
        assert json.loads(await ws.recv())['text'] == 'chunk 1'
        await ws.send('{"type":"stop"}')
        assert json.loads(await ws.recv())['text'] == 'chunk 1'


async def test_context_notes_reach_model_before_ready(streaming_app, server):
    user, session_id = await create_session(streaming_app, server, 'context')
    async with httpx.AsyncClient() as http:
        response = await http.post(server + f'/api/sessions/{session_id}/notes', headers={'Authorization': f'Bearer {user}'}, files={'file': ('notes.pdf', b'%PDF notes', 'application/pdf')})
    assert response.status_code == 200
    async with connect(stream_url(server, session_id, user)) as ws:
        assert json.loads(await ws.recv())['type'] == 'ready'
        assert len(streaming_app.model.notes) == 1
        assert b'%PDF notes' in streaming_app.model.notes[0]
        await ws.send('{"type":"stop"}')
        assert json.loads(await ws.recv())['type'] == 'final'
    assert await streaming_app.db.fetchval('SELECT count(*) FROM session_notes') == 1


async def test_wrong_owner_cannot_connect(streaming_app, server):
    _, session_id = await create_session(streaming_app, server)
    async with connect(stream_url(server, session_id, uuid4())) as ws:
        assert json.loads(await ws.recv()) == {'type': 'error', 'text': 'Session not found'}


async def test_session_duration_limit_finalizes(streaming_app, server, monkeypatch):
    user, session_id = await create_session(streaming_app, server)
    await streaming_app.db.execute("UPDATE sessions SET expires_at=NOW()+INTERVAL '1 second' WHERE id=$1::uuid", session_id)
    async with connect(stream_url(server, session_id, user)) as ws:
        assert json.loads(await ws.recv())['type'] == 'ready'
        await ws.send(wav_chunk())
        assert json.loads(await ws.recv())['type'] == 'caption'
        assert json.loads(await asyncio.wait_for(ws.recv(), 3))['type'] == 'warning'
        assert json.loads(await ws.recv())['type'] == 'final'


async def test_disconnect_still_saves_and_releases_session(streaming_app, server):
    user, session_id = await create_session(streaming_app, server)
    async with connect(stream_url(server, session_id, user)) as ws:
        assert json.loads(await ws.recv())['type'] == 'ready'
        await ws.send(wav_chunk())
        assert json.loads(await ws.recv())['type'] == 'caption'
    async with asyncio.timeout(3):
        while await streaming_app.db.fetchval('SELECT is_active FROM sessions WHERE id=$1::uuid', session_id):
            await asyncio.sleep(0.01)
    row = await streaming_app.db.fetchrow('SELECT transcript_key,stream_id FROM sessions WHERE id=$1::uuid', session_id)
    assert row['transcript_key'] and row['stream_id'] is None


async def test_model_setup_failure_releases_claim(streaming_app, server):
    user, session_id = await create_session(streaming_app, server)
    streaming_app.model.fail_init = True
    async with connect(stream_url(server, session_id, user)) as ws:
        message = json.loads(await ws.recv())
        assert message['type'] == 'error'
    row = await streaming_app.db.fetchrow('SELECT is_active,stream_id,error FROM sessions WHERE id=$1::uuid', session_id)
    assert not row['is_active'] and row['stream_id'] is None and row['error']


async def test_stale_worker_lease_is_recovered_without_reusing_model_context(database):
    user = uuid4()
    await database.execute('INSERT INTO auth.users (id) VALUES ($1)', user)
    original = await sessions_db.create_session(database, user, 'baseline')
    stream_id = uuid4()
    assert await sessions_db.claim_stream(database, original.id, user, stream_id)
    await database.execute("UPDATE sessions SET stream_lease_expires_at=NOW()-INTERVAL '1 second' WHERE id=$1", original.id)
    assert await sessions_db.claim_stream(database, original.id, user, uuid4()) is None
    assert await sessions_db.get_active_session(database, user) is None
    replacement = await sessions_db.create_session(database, user, 'baseline')
    assert replacement.id != original.id
    assert not await sessions_db.refresh_stream(database, original.id, stream_id)


async def test_repaired_migrations_handle_legacy_duplicates_and_can_be_reapplied(database):
    from pathlib import Path
    user = uuid4()
    await database.execute('INSERT INTO auth.users (id) VALUES ($1)', user)
    await database.execute('DROP INDEX one_active_session_per_user')
    await database.execute("INSERT INTO sessions(user_id,mode) VALUES ($1,'baseline'),($1,'context')", user)
    directory = Path(__file__).parents[2] / 'app/migrations'
    for _ in range(2):
        for name in ['002_add_pgcron.sql', '003_add_partial_index.sql', '004_session_notes.sql', '005_stream_leases.sql', '006_dashboard_library.sql']:
            await database.execute((directory / name).read_text())
    assert await database.fetchval('SELECT count(*) FROM sessions WHERE user_id=$1 AND is_active=TRUE', user) == 1


async def test_chunk_heartbeat_does_not_shorten_hard_expiry(database):
    user = uuid4()
    await database.execute('INSERT INTO auth.users (id) VALUES ($1)', user)
    session = await sessions_db.create_session(database, user, 'baseline')
    stream_id = uuid4()
    assert await sessions_db.claim_stream(database, session.id, user, stream_id)
    for _ in range(3):
        assert await sessions_db.refresh_stream(database, session.id, stream_id)
    assert await database.fetchval('SELECT expires_at FROM sessions WHERE id=$1', session.id) == session.expires_at


async def test_inactivity_timeout_saves_transcript_and_releases_stream(streaming_app, server, monkeypatch):
    monkeypatch.setattr(get_settings(), 'SESSION_TIMEOUT_SECONDS', 0.1)
    user, session_id = await create_session(streaming_app, server)
    async with connect(stream_url(server, session_id, user)) as ws:
        assert json.loads(await ws.recv())['type'] == 'ready'
        assert json.loads(await asyncio.wait_for(ws.recv(), 3))['type'] == 'error'
    row = await streaming_app.db.fetchrow('SELECT is_active,stream_id,transcript_key FROM sessions WHERE id=$1::uuid', session_id)
    assert not row['is_active'] and row['stream_id'] is None and row['transcript_key']


async def test_session_names_are_unique_across_history_and_normalized(streaming_app, server):
    user, first_id = await create_session(streaming_app, server)
    original = await sessions_db.get_session(streaming_app.db, UUID(first_id), user)
    await sessions_db.end_session(streaming_app.db, original.id, user)
    async with httpx.AsyncClient() as http:
        duplicate = await http.post(server + '/api/sessions', headers={'Authorization': f'Bearer {user}'}, json={'mode': 'baseline', 'name': f'  {original.name.upper()}  '})
        assert duplicate.status_code == 409
        assert 'name' in duplicate.json()['detail']
        distinct = await http.post(server + '/api/sessions', headers={'Authorization': f'Bearer {user}'}, json={'mode': 'baseline', 'name': 'A different lecture'})
        assert distinct.status_code == 200
        history = await http.get(server + '/api/sessions', headers={'Authorization': f'Bearer {user}'})
        assert len(history.json()) == 2
        assert sum(row['is_active'] for row in history.json()) == 1


async def test_files_transcripts_and_library_persist_until_explicit_deletion(streaming_app, server):
    user, session_id = await create_session(streaming_app, server)
    headers = {'Authorization': f'Bearer {user}'}
    async with httpx.AsyncClient() as http:
        upload = await http.post(server + f'/api/sessions/{session_id}/notes', headers=headers, files={'file': ('lecture.pdf', b'%PDF lecture materials', 'application/pdf')})
        assert upload.status_code == 200
    async with connect(stream_url(server, session_id, user)) as ws:
        assert json.loads(await ws.recv())['type'] == 'ready'
        await ws.send(wav_chunk())
        assert json.loads(await ws.recv())['type'] == 'caption'
        await ws.send('{"type":"stop"}')
        assert json.loads(await ws.recv())['transcript_saved']
    async with httpx.AsyncClient() as http:
        details = (await http.get(server + f'/api/sessions/{session_id}', headers=headers)).json()
        assert details['transcript_text'] == 'chunk 0' and not details['is_active']
        library_response = await http.get(server + '/api/library', headers=headers)
        assert library_response.status_code == 200, library_response.text
        library = library_response.json()
        assert library[0]['filename'] == 'lecture.pdf' and library[0]['session_id'] == session_id
        assert (await http.get(server + f'/api/sessions/{session_id}/notes/lecture.pdf', headers=headers)).content == b'%PDF lecture materials'
        assert (await http.get(server + f'/api/sessions/{session_id}/download', headers=headers)).content.startswith(b'%PDF')
        assert (await http.delete(server + f'/api/sessions/{session_id}', headers=headers)).status_code == 200
        assert (await http.get(server + '/api/library', headers=headers)).json() == []
        assert (await http.get(server + '/api/sessions', headers=headers)).json() == []
    assert not streaming_app.storage.files


async def test_account_plan_is_admin_managed_and_claim_rechecks_it(database):
    user = uuid4()
    await database.execute('INSERT INTO auth.users(id) VALUES ($1)', user)
    assert (await sessions_db.get_account(database, user)).plan == 'free'
    session = await sessions_db.create_session(database, user, 'baseline', 'Plan verification')
    assert session.recording_limit_seconds == 30
    await database.execute("INSERT INTO account_plans(user_id,plan) VALUES ($1,'paid')", user)
    account = await sessions_db.get_account(database, user)
    assert account.plan == 'paid' and account.recording_limit_seconds > 30
    claimed = await sessions_db.claim_stream(database, session.id, user, uuid4())
    assert claimed.recording_limit_seconds == account.recording_limit_seconds


async def test_audio_duration_budget_is_atomic_and_cannot_overrun(database):
    user, stream_id = uuid4(), uuid4()
    await database.execute('INSERT INTO auth.users(id) VALUES ($1)', user)
    session = await sessions_db.create_session(database, user, 'baseline', 'Atomic recording allowance')
    assert await sessions_db.claim_stream(database, session.id, user, stream_id)
    attempts = await asyncio.gather(*(sessions_db.record_audio(database, session.id, stream_id, 10000) for _ in range(5)))
    assert attempts.count(True) == 3
    assert await database.fetchval('SELECT recorded_duration_ms FROM sessions WHERE id=$1', session.id) == 30000


async def test_deletion_and_stream_claim_cannot_both_win(database):
    user = uuid4()
    await database.execute('INSERT INTO auth.users(id) VALUES ($1)', user)
    session = await sessions_db.create_session(database, user, 'baseline', 'Deletion race')
    deleted, claimed = await asyncio.gather(sessions_db.begin_delete(database, session.id, user), sessions_db.claim_stream(database, session.id, user, uuid4()))
    assert deleted != (claimed is not None)
