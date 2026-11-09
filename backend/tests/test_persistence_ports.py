"""REST and streaming compose replaceable stores without cloud clients or SQL."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.caption_store import StoredCaptionStore
from app.core.auth import get_token_verifier, get_user_id
from app.core.config import get_settings
from app.core.dependencies import get_notes_repository, get_object_store, get_session_repository
from app.models.session import AccountOverview, LibraryFile, Session, SessionMode
from app.ports.captioning import ProviderCapabilities
from app.ports.persistence import NotesRepository, ObjectStore, PersistenceConflictError, SessionRepository
from app.providers.chunked import MockTranscriptionProvider
from app.providers.chunked import GroqWhisperProvider
from app.providers.guarded import BudgetedTranscriptionProvider
from app.ports.usage import TranscriptionBudget
from app.routers import audio_router, capabilities_router, sessions_router, workspace_router
from app.utils.storage_helper import cleanup_storage
from tests.helpers import multipart_fields, pdf_notes, wav_audio


class MemoryObjects:
    def __init__(self):
        self.files = {}

    async def put(self, bucket, key, data, *, content_type):
        self.files[bucket, key] = data

    async def get(self, bucket, key):
        return self.files[bucket, key]

    async def delete(self, bucket, keys):
        for key in keys:
            self.files.pop((bucket, key), None)

    async def ensure_bucket(self, bucket):
        pass


@pytest.fixture
def persistence_app():
    now = datetime.now(timezone.utc)
    session = Session(id=uuid4(), user_id=uuid4(), mode="baseline", is_active=True,
                      created_at=now, expires_at=now + timedelta(minutes=5))
    sessions = AsyncMock(spec=SessionRepository)
    async def get(session_id, user_id):
        return session if (session_id, user_id) == (session.id, session.user_id) else None
    sessions.get.side_effect = get
    sessions.get_account.return_value = AccountOverview(plan="free", recording_limit_seconds=30)
    sessions.create_session.return_value = session
    sessions.get_active_session.return_value = session
    sessions.get_all_sessions.return_value = [session]
    sessions.claim.return_value = session
    sessions.refresh.return_value = True
    sessions.finish.return_value = True
    async def set_transcript_key(session_id, user_id, key, text=None):
        assert (session_id, user_id) == (session.id, session.user_id)
        session.transcript_key = key
        session.transcript_text = text
    sessions.set_transcript_key.side_effect = set_transcript_key
    notes = AsyncMock(spec=NotesRepository)
    notes.count_notes.return_value = 0
    notes.list_note_storage_keys.return_value = []
    notes.list_notes.return_value = []
    notes.list_library.return_value = []
    objects = MemoryObjects()
    assert isinstance(objects, ObjectStore)
    app = FastAPI()
    app.state.transcription_provider = MockTranscriptionProvider(delay_ms=0)
    app.include_router(sessions_router.router)
    app.include_router(workspace_router.router)
    app.include_router(audio_router.router)
    app.include_router(capabilities_router.router)
    app.dependency_overrides[get_session_repository] = lambda: sessions
    app.dependency_overrides[get_notes_repository] = lambda: notes
    app.dependency_overrides[get_object_store] = lambda: objects
    app.dependency_overrides[get_user_id] = lambda: session.user_id
    app.dependency_overrides[get_token_verifier] = lambda: SimpleNamespace(verify=lambda _: session.user_id)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, app=app, session=session, sessions=sessions,
                              notes=notes, objects=objects)


def test_session_routes_accept_replacement_repositories(persistence_app):
    p = persistence_app
    assert p.client.post('/api/sessions', json={'mode': 'baseline', 'name': 'Test lecture'}).status_code == 200
    assert p.client.get('/api/sessions').json()[0]['id'] == str(p.session.id)
    assert p.client.get('/api/sessions/active').json()['id'] == str(p.session.id)
    assert p.client.get(f'/api/sessions/{p.session.id}').status_code == 200
    p.sessions.create_session.side_effect = PersistenceConflictError('conflict')
    assert p.client.post('/api/sessions', json={'mode': 'baseline', 'name': 'Test lecture'}).status_code == 409


def test_note_upload_download_delete_use_independent_stores(persistence_app):
    p = persistence_app
    p.app.state.transcription_provider.capabilities = ProviderCapabilities('test', supports_pdf_notes=True)
    url = f'/api/sessions/{p.session.id}/notes'
    response = p.client.post(url, files={'file': ('lecture.pdf', b'%PDF demo', 'application/pdf')})
    assert response.status_code == 200
    metadata = p.notes.save_note.call_args.kwargs
    p.notes.get_note.return_value = metadata['storage_key']
    p.notes.list_notes.return_value = ['lecture.pdf']
    assert p.client.get(url).json() == ['lecture.pdf']
    assert p.client.get(url + '/lecture.pdf').content == b'%PDF demo'
    assert p.client.delete(url + '/lecture.pdf').status_code == 200
    assert not p.objects.files
    p.notes.delete_note.assert_awaited_once_with(
        session_id=p.session.id, user_id=p.session.user_id, filename='lecture.pdf',
    )


async def test_groq_context_flows_from_pdf_upload_through_websocket_and_transcript(persistence_app):
    p = persistence_app
    requests = []
    async def groq_request(request):
        fields = multipart_fields(request, await request.aread())
        requests.append(fields)
        assert fields['prompt'] == 'PostgreSQL, MVCC'
        return httpx.Response(200, json={'text': 'PostgreSQL uses MVCC.'})
    budget = AsyncMock(spec=TranscriptionBudget)
    async with httpx.AsyncClient(transport=httpx.MockTransport(groq_request)) as http:
        provider = GroqWhisperProvider(http, 'test-key')
        p.app.state.transcription_provider = BudgetedTranscriptionProvider(provider, budget, get_settings())
        caps = p.client.get('/api/capabilities').json()
        assert caps['supports_pdf_notes'] and caps['requires_text_notes']
        p.session.mode = SessionMode('context')
        response = p.client.post('/api/sessions', json={'mode': 'context', 'name': 'Database lecture'})
        assert response.status_code == 200
        p.sessions.create_session.assert_awaited_once_with(user_id=p.session.user_id, mode='context', name='Database lecture')
        response = p.client.post(f'/api/sessions/{p.session.id}/notes',
            files={'file': ('lecture.pdf', pdf_notes('PostgreSQL MVCC'), 'application/pdf')})
        assert response.status_code == 200
        metadata = p.notes.save_note.call_args.kwargs
        p.notes.list_note_storage_keys.return_value = [metadata['storage_key']]
        assert requests == []
        with p.client.websocket_connect(f'/ws/sessions/{p.session.id}/stream?access_token=test') as ws:
            assert ws.receive_json()['type'] == 'ready'
            ws.send_bytes(wav_audio())
            assert ws.receive_json()['text'] == 'PostgreSQL uses MVCC.'
            ws.send_json({'type': 'stop'})
            final = ws.receive_json()
            assert final['transcript_saved'] and final['text'] == 'PostgreSQL uses MVCC.'
        assert p.session.transcript_text == 'PostgreSQL uses MVCC.'
        assert p.client.get(f'/api/sessions/{p.session.id}/download').content.startswith(b'%PDF')
        assert len(requests) == 1
        budget.reserve.assert_awaited_once_with(p.session.id, 'transcribe', 10)
        # Finalization releases note context even though the files remain saved.
        with pytest.raises(ValueError, match='text-based PDF'):
            await provider.transcribe(p.session.id, b'wav', 1, 'context')
        assert ('session-pdfs', f'{p.session.user_id}/{p.session.id}/{metadata["storage_key"]}') in p.objects.files


@pytest.mark.parametrize('mode, expected', [('context', 422), ('baseline', 200)])
async def test_groq_validates_note_text_but_keeps_reference_uploads_available(persistence_app, mode, expected):
    p = persistence_app
    p.session.mode = SessionMode(mode)
    async with httpx.AsyncClient() as http:
        p.app.state.transcription_provider = GroqWhisperProvider(http, 'test-key')
        response = p.client.post(f'/api/sessions/{p.session.id}/notes',
            files={'file': ('scanned.pdf', pdf_notes(''), 'application/pdf')})
    assert response.status_code == expected
    if mode == 'context':
        assert 'OCR' in response.json()['detail']
        assert not p.objects.files
        p.notes.save_note.assert_not_awaited()
    else:
        p.notes.save_note.assert_awaited_once()


def test_stream_saves_pdf_and_rest_downloads_from_same_object_store(persistence_app):
    p = persistence_app
    with p.client.websocket_connect(f'/ws/sessions/{p.session.id}/stream?access_token=test') as ws:
        assert ws.receive_json()['type'] == 'ready'
        ws.send_bytes(wav_audio())
        assert ws.receive_json()['text'] == 'Test caption 0'
        ws.send_json({'type': 'stop'})
        assert ws.receive_json()['transcript_saved']
    response = p.client.get(f'/api/sessions/{p.session.id}/download')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert response.content.startswith(b'%PDF')
    assert response.content == p.objects.files['transcripts', p.session.transcript_key]


def test_wrong_owner_cannot_read_notes_or_transcript(persistence_app):
    p = persistence_app
    p.app.dependency_overrides[get_user_id] = lambda: uuid4()
    assert p.client.get(f'/api/sessions/{p.session.id}/notes').status_code == 404
    assert p.client.get(f'/api/sessions/{p.session.id}/download').status_code == 404
    p.notes.list_notes.assert_not_awaited()


async def test_cleanup_keeps_metadata_when_object_deletion_fails():
    notes, objects = AsyncMock(spec=NotesRepository), AsyncMock(spec=ObjectStore)
    notes.list_note_storage_keys.return_value = ['note.pdf']
    objects.delete.side_effect = RuntimeError('store down')
    await cleanup_storage(uuid4(), notes, objects, uuid4())
    notes.delete_all_notes.assert_not_awaited()


async def test_transcript_upload_failure_does_not_publish_key(persistence_app):
    p = persistence_app
    objects = AsyncMock(spec=ObjectStore)
    objects.put.side_effect = RuntimeError('store down')
    store = StoredCaptionStore(p.sessions, p.notes, objects)
    with pytest.raises(RuntimeError, match='store down'):
        await store.save_transcript(p.session, 'demo')
    p.sessions.set_transcript_key.assert_not_awaited()
    p.sessions.save_transcript_text.assert_awaited_once_with(p.session.id, p.session.user_id, "demo")


def test_named_session_validation_and_read_only_plan(persistence_app):
    p = persistence_app
    for name in ('', '   ', 'x' * 121):
        assert p.client.post('/api/sessions', json={'name': name, 'mode': 'baseline'}).status_code == 422
    assert p.client.post('/api/sessions', json={'name': '  Week   One  ', 'mode': 'baseline'}).status_code == 200
    assert p.sessions.create_session.call_args.kwargs['name'] == 'Week One'
    assert p.client.get('/api/account').json() == {'plan': 'free', 'recording_limit_seconds': 30, 'demo_mode': False, 'transcription_enabled': True}
    assert p.client.post('/api/account', json={'plan': 'paid'}).status_code == 405


def test_completed_session_files_remain_accessible(persistence_app):
    p = persistence_app
    p.session.is_active = False
    key = f'{p.session.user_id}/{p.session.id}/file.pdf'
    p.objects.files['session-pdfs', key] = b'%PDF retained'
    p.notes.get_note.return_value = 'file.pdf'
    p.notes.list_notes.return_value = ['lecture.pdf']
    p.notes.list_library.return_value = [LibraryFile(id=uuid4(), session_id=p.session.id, session_name=p.session.name, filename='lecture.pdf', created_at=p.session.created_at)]
    assert p.client.get(f'/api/sessions/{p.session.id}/notes').json() == ['lecture.pdf']
    assert p.client.get(f'/api/sessions/{p.session.id}/notes/lecture.pdf').content == b'%PDF retained'
    assert p.client.get('/api/library').json()[0]['session_id'] == str(p.session.id)


def test_deletion_failure_preserves_record_for_retry(persistence_app):
    p = persistence_app
    p.sessions.begin_delete.return_value = True
    p.notes.list_note_storage_keys.return_value = ['file.pdf']
    async def fail(*args):
        raise RuntimeError('unavailable')
    p.objects.delete = fail
    assert p.client.delete(f'/api/sessions/{p.session.id}').status_code == 503
    p.sessions.delete_session.assert_not_awaited()


def test_live_session_cannot_be_deleted(persistence_app):
    p = persistence_app
    p.sessions.begin_delete.return_value = False
    assert p.client.delete(f'/api/sessions/{p.session.id}').status_code == 409
    p.sessions.delete_session.assert_not_awaited()
