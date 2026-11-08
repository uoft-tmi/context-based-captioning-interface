"""Exercise the actual WebSocket route entirely through replacement application ports."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_token_verifier
from app.core.dependencies import get_caption_store, get_stream_sessions, get_transcription_provider
from app.core.exceptions import ProviderRequestError
from app.core.exceptions import DemoAccessDenied
from app.models.session import Session
from app.ports.captioning import CaptionStore, StreamSessionRepository, TokenVerifier
from app.providers.chunked import MockTranscriptionProvider
from app.routers import audio_router, capabilities_router
from tests.helpers import wav_audio


class MemorySessions:
    def __init__(self, session):
        self.session = session
        self.owner = None
        self.recorded_ms = 0

    async def record_audio(self, session_id, stream_id, duration_ms):
        if stream_id != self.owner or self.recorded_ms + duration_ms > self.session.recording_limit_seconds * 1000:
            return False
        self.recorded_ms += duration_ms
        return True

    async def get(self, session_id, user_id):
        return self.session if (session_id, user_id) == (self.session.id, self.session.user_id) else None

    async def claim(self, session_id, user_id, stream_id):
        if not await self.get(session_id, user_id) or self.owner is not None or not self.session.is_active:
            return None
        self.owner = stream_id
        return self.session

    async def refresh(self, session_id, stream_id, *, require_active=True):
        return session_id == self.session.id and stream_id == self.owner and (self.session.is_active or not require_active)

    async def finish(self, session_id, stream_id, error=None):
        if stream_id != self.owner:
            return False
        self.session.is_active = False
        self.session.error = error
        self.owner = None
        return True


class MemoryCaptions:
    def __init__(self):
        self.transcript = None
        self.cleaned = False

    async def load_notes(self, session):
        return []

    async def save_transcript(self, session, transcript):
        self.transcript = transcript

    async def cleanup_notes(self, session):
        self.cleaned = True


class TestTokenVerifier:
    def verify(self, token):
        return UUID(token)


@pytest.fixture
def isolated_stream():
    now = datetime.now(timezone.utc)
    session = Session(id=uuid4(), user_id=uuid4(), mode="baseline", is_active=True,
                      created_at=now, expires_at=now + timedelta(minutes=5))
    sessions = MemorySessions(session)
    store = MemoryCaptions()
    provider = MockTranscriptionProvider(delay_ms=0)
    verifier = TestTokenVerifier()
    assert isinstance(sessions, StreamSessionRepository)
    assert isinstance(store, CaptionStore)
    assert isinstance(verifier, TokenVerifier)
    app = FastAPI()
    app.include_router(audio_router.router)
    app.include_router(capabilities_router.router)
    app.dependency_overrides[get_stream_sessions] = lambda: sessions
    app.dependency_overrides[get_caption_store] = lambda: store
    app.dependency_overrides[get_transcription_provider] = lambda: provider
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    return app, session, sessions, store, provider


def test_entire_stream_accepts_replacement_ports_without_database_or_supabase(isolated_stream):
    app, session, sessions, store, _ = isolated_stream
    with TestClient(app) as http:
        capabilities = http.get('/api/capabilities').json()
        assert capabilities['name'] == 'mock'
        assert not capabilities['supports_pdf_notes']
        with http.websocket_connect(f'/ws/sessions/{session.id}/stream?access_token={session.user_id}') as ws:
            assert ws.receive_json()['type'] == 'ready'
            ws.send_bytes(wav_audio())
            assert ws.receive_json()['text'] == 'Test caption 0'
            ws.send_json({'type': 'stop'})
            message = ws.receive_json()
            assert message['type'] == 'final'
            assert message['transcript_saved']
            assert store.transcript == 'Test caption 0'
            assert not session.is_active
            assert sessions.owner is None
            assert store.cleaned


def test_unapproved_websocket_never_claims_session_or_starts_provider(isolated_stream):
    app, session, sessions, store, provider = isolated_stream
    class DeniedVerifier:
        def verify(self, token):
            raise DemoAccessDenied('This demo is restricted to the approved account.')
    app.dependency_overrides[get_token_verifier] = lambda: DeniedVerifier()
    with TestClient(app) as http:
        with http.websocket_connect(f'/ws/sessions/{session.id}/stream?access_token=denied') as ws:
            message = ws.receive_json()
            assert message == {'type': 'error', 'text': 'This demo is restricted to the approved account.'}
    assert sessions.owner is None
    assert store.transcript is None
    assert session.is_active


def test_permanent_provider_failure_is_visible_and_session_is_released(isolated_stream):
    app, session, sessions, store, provider = isolated_stream
    async def fail(*args):
        raise ProviderRequestError('groq rate limit reached')
    provider.transcribe = fail
    with TestClient(app) as http:
        with http.websocket_connect(f'/ws/sessions/{session.id}/stream?access_token={session.user_id}') as ws:
            assert ws.receive_json()['type'] == 'ready'
            ws.send_bytes(wav_audio())
            assert ws.receive_json() == {'type': 'error', 'text': 'groq rate limit reached'}
    assert session.error == 'groq rate limit reached'
    assert not session.is_active and sessions.owner is None
    assert store.transcript == ''


def test_wrong_owner_is_rejected_using_injected_verifier(isolated_stream):
    app, session, sessions, store, _ = isolated_stream
    with TestClient(app) as http:
        with http.websocket_connect(f'/ws/sessions/{session.id}/stream?access_token={uuid4()}') as ws:
            assert ws.receive_json() == {'type': 'error', 'text': 'Session not found'}
    assert session.is_active and sessions.owner is None and store.transcript is None


def test_binary_wav_frames_preserve_audio_order_and_final_transcript(isolated_stream):
    app, session, sessions, store, provider = isolated_stream
    received = []
    transcribe = provider.transcribe

    async def capture(session_id, audio, chunk_index, mode):
        received.append((chunk_index, audio))
        return await transcribe(session_id, audio, chunk_index, mode)

    provider.transcribe = capture
    frames = [wav_audio(0.01), wav_audio(0.02)]
    with TestClient(app) as http:
        with http.websocket_connect(f'/ws/sessions/{session.id}/stream?access_token={session.user_id}') as ws:
            assert ws.receive_json()['type'] == 'ready'
            for index, frame in enumerate(frames):
                ws.send_bytes(frame)
                caption = ws.receive_json()
                assert caption['chunk_index'] == index
                assert caption['text'] == f'Test caption {index}'
            ws.send_json({'type': 'stop'})
            final = ws.receive_json()
            assert final['transcript_saved']
            assert final['text'] == 'Test caption 0 Test caption 1'
    assert received == list(enumerate(frames))
    assert store.transcript == final['text']
    assert not session.is_active and sessions.owner is None


def test_free_recording_is_capped_and_finalized_without_a_client_stop(isolated_stream):
    import io
    import wave
    app, session, sessions, store, provider = isolated_stream
    durations = []
    original = provider.transcribe

    async def record(session_id, audio, chunk_index, mode):
        with wave.open(io.BytesIO(audio), 'rb') as wav:
            durations.append(wav.getnframes() / wav.getframerate())
        return await original(session_id, audio, chunk_index, mode)

    provider.transcribe = record
    with TestClient(app) as http:
        with http.websocket_connect(f'/ws/sessions/{session.id}/stream?access_token={session.user_id}') as ws:
            assert ws.receive_json()['type'] == 'ready'
            for _ in range(3):
                ws.send_bytes(wav_audio(12))
                assert ws.receive_json()['type'] == 'caption'
            assert ws.receive_json()['transcript_saved']
    assert durations == [12, 12, 6]
    assert session.recorded_duration_ms == 30000
    assert not session.is_active and store.transcript


def test_paid_recording_can_continue_beyond_thirty_seconds(isolated_stream):
    app, session, sessions, store, _ = isolated_stream
    session.recording_limit_seconds = 60
    with TestClient(app) as http:
        with http.websocket_connect(f'/ws/sessions/{session.id}/stream?access_token={session.user_id}') as ws:
            assert ws.receive_json()['type'] == 'ready'
            for _ in range(3):
                ws.send_bytes(wav_audio(12))
                assert ws.receive_json()['type'] == 'caption'
            ws.send_json({'type': 'stop'})
            assert ws.receive_json()['transcript_saved']
    assert session.recorded_duration_ms == 36000
