from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.models.session import Session, SessionMode
from app.services import session_service


def _make_upload_file(filename: str, content_type: str, payload: bytes) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(payload),
        headers=Headers({"content-type": content_type}),
    )


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


@pytest.mark.asyncio
async def test_create_session_deactivates_existing_then_creates():
    db = AsyncMock()
    created = AsyncMock()

    with (
        patch(
            "app.services.session_service.sessions_db.deactivate_sessions",
            new=AsyncMock(),
        ) as deactivate_sessions,
        patch(
            "app.services.session_service.sessions_db.create_session",
            new=AsyncMock(return_value=created),
        ) as create_session,
    ):
        result = await session_service.create_session(
            db=db,
            user_id=str(uuid4()),
            mode=SessionMode.context,
        )

    assert result is created
    deactivate_sessions.assert_awaited_once()
    create_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_session_not_found_raises_404():
    db = AsyncMock()
    with patch(
        "app.services.session_service.sessions_db.get_session",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await session_service.get_session(
                db=db,
                session_id=str(uuid4()),
                user_id=str(uuid4()),
            )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_upload_note_rejects_non_pdf(session: Session):
    file = _make_upload_file("note.txt", "text/plain", b"abc")

    with pytest.raises(HTTPException) as exc:
        await session_service.upload_note(
            file=file,
            session=session,
            supabase_client=AsyncMock(),
            db=AsyncMock(),
        )

    assert exc.value.status_code == 400
    assert "Only PDF" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_upload_note_persists_metadata_and_uploads_file(session: Session):
    file = _make_upload_file("note.pdf", "application/pdf", b"%PDF content")
    supabase_bucket = SimpleNamespace(upload=AsyncMock())
    supabase_client = SimpleNamespace(
        storage=SimpleNamespace(from_=Mock(return_value=supabase_bucket))
    )
    db = AsyncMock()

    with (
        patch(
            "app.services.session_service.notes_db.count_notes",
            new=AsyncMock(return_value=0),
        ),
        patch(
            "app.services.session_service.notes_db.save_note",
            new=AsyncMock(),
        ) as save_note,
    ):
        result = await session_service.upload_note(
            file=file,
            session=session,
            supabase_client=cast(Any, supabase_client),
            db=db,
        )

    assert result == {"status": "processed"}
    save_note.assert_awaited_once()
    supabase_bucket.upload.assert_awaited_once()


@pytest.mark.asyncio
async def test_end_session_marks_db_and_cleans_storage(session: Session):
    db = AsyncMock()
    supabase_client = AsyncMock()

    with (
        patch(
            "app.services.session_service.sessions_db.end_session",
            new=AsyncMock(),
        ) as end_session,
        patch(
            "app.services.session_service.cleanup_storage",
            new=AsyncMock(),
        ) as cleanup_storage,
    ):
        result = await session_service.end_session(
            session=session,
            supabase_client=supabase_client,
            db=db,
        )

    assert result["session_id"] == str(session.id)
    end_session.assert_awaited_once_with(
        db=db,
        session_id=session.id,
        user_id=session.user_id,
    )
    cleanup_storage.assert_awaited_once_with(
        user_id=session.user_id,
        session_id=session.id,
        supabase_client=supabase_client,
        db=db,
    )


@pytest.mark.asyncio
async def test_slide_expiry_wraps_internal_errors():
    db = AsyncMock()

    with patch(
        "app.services.session_service.sessions_db.slide_expiry",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        with pytest.raises(HTTPException) as exc:
            await session_service.slide_expiry(db=db, session_id=str(uuid4()))

    assert exc.value.status_code == 500
    assert "db down" in str(exc.value.detail)
