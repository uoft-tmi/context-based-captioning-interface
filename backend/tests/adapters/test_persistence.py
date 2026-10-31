from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from asyncpg import UniqueViolationError

from app.adapters.object_store import SupabaseObjectStore
from app.adapters.repositories import PostgresNotesRepository, PostgresSessionRepository
from app.ports.persistence import NotesRepository, ObjectStore, PersistenceConflictError, SessionRepository


async def test_supabase_object_store_preserves_keys_bytes_and_upsert():
    bucket = SimpleNamespace(upload=AsyncMock(), download=AsyncMock(return_value=b'pdf'), remove=AsyncMock())
    client = SimpleNamespace(storage=SimpleNamespace(from_=Mock(return_value=bucket)))
    store = SupabaseObjectStore(client)
    assert isinstance(store, ObjectStore)
    await store.put('notes', 'user/session/file.pdf', b'pdf', content_type='application/pdf')
    bucket.upload.assert_awaited_once_with(
        'user/session/file.pdf', b'pdf', {'content-type': 'application/pdf', 'upsert': 'true'},
    )
    assert await store.get('notes', 'user/session/file.pdf') == b'pdf'
    await store.delete('notes', ('user/session/file.pdf',))
    bucket.remove.assert_awaited_once_with(['user/session/file.pdf'])
    await store.delete('notes', [])
    assert bucket.remove.await_count == 1
    assert all(call.args == ('notes',) for call in client.storage.from_.call_args_list)


async def test_supabase_bucket_creation_is_private_and_tolerates_concurrent_creation():
    storage = SimpleNamespace(
        get_bucket=AsyncMock(side_effect=[RuntimeError('missing'), {}]),
        create_bucket=AsyncMock(side_effect=RuntimeError('already exists')),
    )
    await SupabaseObjectStore(SimpleNamespace(storage=storage)).ensure_bucket('transcripts')
    storage.create_bucket.assert_awaited_once_with('transcripts', options={'public': False})
    assert storage.get_bucket.await_count == 2


async def test_supabase_bucket_errors_are_not_silently_ignored():
    storage = SimpleNamespace(
        get_bucket=AsyncMock(side_effect=RuntimeError('unavailable')),
        create_bucket=AsyncMock(side_effect=RuntimeError('unavailable')),
    )
    with pytest.raises(RuntimeError, match='unavailable'):
        await SupabaseObjectStore(SimpleNamespace(storage=storage)).ensure_bucket('transcripts')


async def test_database_conflicts_are_translated_to_application_errors():
    sessions, notes = PostgresSessionRepository(Mock()), PostgresNotesRepository(Mock())
    assert isinstance(sessions, SessionRepository)
    assert isinstance(notes, NotesRepository)
    with patch('app.adapters.repositories.sessions_db.create_session', new=AsyncMock(side_effect=UniqueViolationError('duplicate'))):
        with pytest.raises(PersistenceConflictError):
            await sessions.create_session(uuid4(), 'baseline')
    with patch('app.adapters.repositories.notes_db.save_note', new=AsyncMock(side_effect=UniqueViolationError('duplicate'))):
        with pytest.raises(PersistenceConflictError):
            await notes.save_note(uuid4(), uuid4(), 'lecture.pdf', 'file.pdf')
