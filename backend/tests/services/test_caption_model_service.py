from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from app.core.exceptions import ModelUnavailableError
from app.models.session import Session, SessionMode
from app.services.caption_model_service import CaptionModelService


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def session() -> Session:
    now = datetime.now(timezone.utc)
    return Session(
        id=uuid4(),
        user_id=uuid4(),
        mode=SessionMode.context,
        is_active=True,
        error=None,
        created_at=now,
        expires_at=now,
        finalized_at=None,
        transcript_key=None,
    )


@pytest.fixture
def baseline_session(session: Session) -> Session:
    return session.model_copy(update={"mode": SessionMode.baseline})


@pytest.fixture
def service_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(service_client: AsyncMock) -> CaptionModelService:
    return CaptionModelService(service_client)


@pytest.fixture
def supabase_chain() -> tuple[SimpleNamespace, AsyncMock, AsyncMock]:
    session_pdfs_bucket = SimpleNamespace(download=AsyncMock())
    transcripts_bucket = SimpleNamespace(upload=AsyncMock())
    from_bucket = Mock(
        side_effect=lambda bucket: (
            session_pdfs_bucket if bucket == "session-pdfs" else transcripts_bucket
        )
    )
    storage = SimpleNamespace(
        from_=from_bucket,
        get_bucket=AsyncMock(),
        create_bucket=AsyncMock(),
    )
    supabase = SimpleNamespace(storage=storage)
    return supabase, session_pdfs_bucket.download, transcripts_bucket.upload


@pytest.mark.asyncio
async def test_upload_notes_skips_non_context_mode(
    service: CaptionModelService,
    baseline_session: Session,
    service_client: AsyncMock,
):
    db = AsyncMock()
    supabase = AsyncMock()

    with patch(
        "app.services.caption_model_service.notes_db.list_note_storage_keys",
        new=AsyncMock(return_value=["a.pdf"]),
    ) as list_keys:
        await service.upload_notes(
            session=baseline_session,
            db=db,
            supabase=supabase,
        )

    list_keys.assert_not_awaited()
    service_client.process_notes.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_notes_reads_supabase_files_and_sends_to_model(
    service: CaptionModelService,
    session: Session,
    supabase_chain: tuple[SimpleNamespace, AsyncMock, AsyncMock],
    service_client: AsyncMock,
):
    supabase, download, _ = supabase_chain
    db = AsyncMock()

    with patch(
        "app.services.caption_model_service.notes_db.list_note_storage_keys",
        new=AsyncMock(return_value=["one.pdf", "two.pdf"]),
    ):
        download.side_effect = [b"pdf-1", b"pdf-2"]

        await service.upload_notes(
            session=session,
            db=db,
            supabase=cast(Any, supabase),
        )

    download.assert_any_await(f"{session.user_id}/{session.id}/one.pdf")
    download.assert_any_await(f"{session.user_id}/{session.id}/two.pdf")
    assert service_client.process_notes.await_count == 2


@pytest.mark.asyncio
async def test_finalize_uses_model_transcript_and_persists(
    service: CaptionModelService,
    session: Session,
    supabase_chain: tuple[SimpleNamespace, AsyncMock, AsyncMock],
    service_client: AsyncMock,
):
    supabase, _, upload = supabase_chain
    conn = AsyncMock()
    db = cast(Any, SimpleNamespace(acquire=lambda: _AcquireCtx(conn)))

    service_client.finalize.return_value = SimpleNamespace(
        final_transcript="hello world"
    )

    transcript = await service.finalize(
        session=session,
        transcript_chunks=["fallback"],
        db=db,
        supabase=cast(Any, supabase),
    )

    assert transcript == "hello world"
    upload.assert_awaited_once()
    supabase.storage.get_bucket.assert_awaited_once_with("transcripts")
    supabase.storage.create_bucket.assert_not_awaited()
    conn.execute.assert_awaited_once()
    execute_args = conn.execute.await_args.args
    assert execute_args[1] == f"transcripts/{session.user_id}/{session.id}.pdf"
    assert execute_args[2] == session.id


@pytest.mark.asyncio
async def test_finalize_creates_transcripts_bucket_when_missing(
    service: CaptionModelService,
    session: Session,
    supabase_chain: tuple[SimpleNamespace, AsyncMock, AsyncMock],
    service_client: AsyncMock,
):
    supabase, _, upload = supabase_chain
    conn = AsyncMock()
    db = cast(Any, SimpleNamespace(acquire=lambda: _AcquireCtx(conn)))

    supabase.storage.get_bucket.side_effect = [RuntimeError("missing"), None]
    service_client.finalize.return_value = SimpleNamespace(final_transcript="hello")

    transcript = await service.finalize(
        session=session,
        transcript_chunks=[],
        db=db,
        supabase=cast(Any, supabase),
    )

    assert transcript == "hello"
    supabase.storage.create_bucket.assert_awaited_once()
    upload.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_falls_back_when_model_unavailable(
    service: CaptionModelService,
    session: Session,
    supabase_chain: tuple[SimpleNamespace, AsyncMock, AsyncMock],
    service_client: AsyncMock,
):
    supabase, _, upload = supabase_chain
    conn = AsyncMock()
    db = cast(Any, SimpleNamespace(acquire=lambda: _AcquireCtx(conn)))

    service_client.finalize.side_effect = ModelUnavailableError("down")

    transcript = await service.finalize(
        session=session,
        transcript_chunks=["one", "two", "three"],
        db=db,
        supabase=cast(Any, supabase),
    )

    assert transcript == "one two three"
    upload.assert_awaited_once()


@pytest.mark.asyncio
async def test_end_session_and_cleanup_calls_db_and_storage(
    service: CaptionModelService,
    session: Session,
):
    db = AsyncMock()
    supabase = AsyncMock()

    with (
        patch(
            "app.services.caption_model_service.sessions_db.end_session",
            new=AsyncMock(),
        ) as end_session,
        patch(
            "app.services.caption_model_service.cleanup_storage",
            new=AsyncMock(),
        ) as cleanup,
    ):
        await service.end_session_and_cleanup(
            session=session,
            db=db,
            supabase=supabase,
        )

    end_session.assert_awaited_once_with(
        db=db,
        session_id=session.id,
        user_id=session.user_id,
    )
    cleanup.assert_awaited_once_with(
        user_id=session.user_id,
        session_id=session.id,
        db=db,
        supabase_client=supabase,
    )
