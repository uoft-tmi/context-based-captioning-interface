from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ModelUnavailableError
from app.models.session import Session
from app.ports.captioning import ProviderCapabilities
from app.services.caption_model_service import CaptionModelService


@pytest.fixture
def session():
    now = datetime.now(timezone.utc)
    return Session(id=uuid4(), user_id=uuid4(), mode="baseline", is_active=True,
                   created_at=now, expires_at=now)


@pytest.fixture
def ports():
    provider = AsyncMock()
    provider.capabilities = ProviderCapabilities("fake", supports_pdf_notes=True)
    store = AsyncMock()
    return provider, store


async def test_baseline_does_not_read_notes(session, ports):
    provider, store = ports
    service = CaptionModelService(provider, store)
    await service.start_session(session)
    await service.upload_notes(session)
    provider.start_session.assert_awaited_once_with(session.id, "baseline")
    store.load_notes.assert_not_awaited()
    provider.process_notes.assert_not_awaited()


async def test_context_forwards_notes_through_injected_ports(session, ports):
    provider, store = ports
    session.mode = "context"
    store.load_notes.return_value = [b"pdf-one", b"pdf-two"]
    await CaptionModelService(provider, store).upload_notes(session)
    provider.process_notes.assert_any_await(session.id, b"pdf-one")
    provider.process_notes.assert_any_await(session.id, b"pdf-two")


async def test_context_requires_notes_before_recording(session, ports):
    provider, store = ports
    session.mode = "context"
    store.load_notes.return_value = []
    with pytest.raises(ValueError, match='Upload at least one PDF'):
        await CaptionModelService(provider, store).upload_notes(session)
    provider.process_notes.assert_not_awaited()


async def test_unsupported_context_rejected_before_provider_start(session, ports):
    provider, store = ports
    provider.capabilities = ProviderCapabilities("baseline", supports_pdf_notes=False)
    session.mode = "context"
    with pytest.raises(ValueError, match="baseline"):
        await CaptionModelService(provider, store).start_session(session)
    provider.start_session.assert_not_awaited()


async def test_transcribe_uses_provider_independently_of_storage(session, ports):
    provider, store = ports
    provider.transcribe.return_value = "a lecture caption"
    assert await CaptionModelService(provider, store).transcribe(session, b"wav", 2) == "a lecture caption"
    provider.transcribe.assert_awaited_once_with(session.id, b"wav", 2, "baseline")
    store.save_transcript.assert_not_awaited()


async def test_final_transcript_saved_through_store_port(session, ports):
    provider, store = ports
    provider.finalize.return_value = "final lecture text"
    assert await CaptionModelService(provider, store).finalize(session, ["partial"]) == "final lecture text"
    store.save_transcript.assert_awaited_once_with(session, "final lecture text")


async def test_unavailable_model_preserves_successful_chunks(session, ports):
    provider, store = ports
    provider.finalize.side_effect = ModelUnavailableError("offline")
    assert await CaptionModelService(provider, store).finalize(session, ["one", "two"]) == "one two"
    store.save_transcript.assert_awaited_once_with(session, "one two")


async def test_storage_failure_is_not_hidden(session, ports):
    provider, store = ports
    provider.finalize.return_value = "lecture"
    store.save_transcript.side_effect = RuntimeError("storage unavailable")
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await CaptionModelService(provider, store).finalize(session, ["lecture"])


async def test_cleanup_uses_injected_store(session, ports):
    provider, store = ports
    await CaptionModelService(provider, store).cleanup_notes(session)
    store.cleanup_notes.assert_awaited_once_with(session)
