from uuid import uuid4

import httpx
import pytest

from app.providers.chunked import GroqWhisperProvider
from tests.helpers import multipart_fields, pdf_notes


async def test_context_includes_vocabulary_from_multiple_pdfs_on_every_chunk():
    requests = []
    async def handle(request):
        requests.append(multipart_fields(request, await request.aread()))
        return httpx.Response(200, json={'text': 'lecture caption'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = GroqWhisperProvider(http, 'test-key')
        session = uuid4()
        await provider.start_session(session, 'context')
        await provider.process_notes(session, pdf_notes('PostgreSQL B-trees'))
        await provider.process_notes(session, pdf_notes('MVCC serializability'))
        assert requests == []
        for index in range(2):
            assert await provider.transcribe(session, b'wav', index, 'context') == 'lecture caption'
        assert await provider.finalize(session, ['first', 'second']) == 'first second'
    assert len(requests) == 2
    for request in requests:
        assert request['prompt'] == 'PostgreSQL, B-trees, MVCC, serializability'
        assert request['model'] == 'whisper-large-v3-turbo'
        assert 'pdf' not in request


async def test_notes_are_isolated_between_sessions_and_ignored_in_baseline_mode():
    prompts = []
    async def handle(request):
        fields = multipart_fields(request, await request.aread())
        prompts.append(fields.get('prompt'))
        return httpx.Response(200, json={'text': 'caption'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = GroqWhisperProvider(http, 'test-key')
        first, second = uuid4(), uuid4()
        await provider.start_session(first, 'context')
        await provider.start_session(second, 'context')
        await provider.process_notes(first, pdf_notes('PostgreSQL'))
        await provider.process_notes(second, pdf_notes('Mitochondria'))
        await provider.transcribe(first, b'wav', 0, 'context')
        await provider.transcribe(second, b'wav', 0, 'context')
        await provider.transcribe(first, b'wav', 1, 'baseline')
        assert prompts == ['PostgreSQL', 'Mitochondria', None]
        await provider.finalize(first, [])
        with pytest.raises(ValueError, match='text-based PDF'):
            await provider.transcribe(first, b'wav', 2, 'context')
        await provider.transcribe(second, b'wav', 1, 'context')
        assert prompts[-1] == 'Mitochondria'
        # A restarted stream cannot inherit notes from its previous attempt.
        await provider.start_session(second, 'baseline')
        with pytest.raises(ValueError, match='text-based PDF'):
            await provider.transcribe(second, b'wav', 2, 'context')


async def test_missing_or_unreadable_context_does_not_call_groq():
    def no_request(request):
        pytest.fail('Invalid or missing context must not spend provider quota')
    async with httpx.AsyncClient(transport=httpx.MockTransport(no_request)) as http:
        provider = GroqWhisperProvider(http, 'test-key')
        session = uuid4()
        await provider.start_session(session, 'context')
        with pytest.raises(ValueError, match='text-based PDF'):
            await provider.transcribe(session, b'wav', 0, 'context')
        with pytest.raises(ValueError, match='could not be read'):
            await provider.process_notes(session, b'invalid PDF')
        await provider.finalize(session, [])
        with pytest.raises(ValueError, match='Start a lecture-notes session'):
            await provider.process_notes(session, pdf_notes('PostgreSQL'))
