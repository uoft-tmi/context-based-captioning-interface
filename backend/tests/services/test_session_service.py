from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock, patch
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
async def test_create_session_uses_repository():
    sessions = AsyncMock()
    user_id = uuid4()
    result = await session_service.create_session(sessions, user_id, SessionMode.context, "Lecture")
    assert result is sessions.create_session.return_value
    sessions.create_session.assert_awaited_once_with(user_id=user_id, mode=SessionMode.context, name="Lecture")


@pytest.mark.asyncio
async def test_get_session_not_found_raises_404():
    sessions = AsyncMock()
    sessions.get.return_value = None
    with pytest.raises(HTTPException) as exc:
        await session_service.get_session(sessions, uuid4(), uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_upload_note_rejects_non_pdf(session: Session):
    file = _make_upload_file("note.txt", "text/plain", b"abc")
    objects, notes = AsyncMock(), AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await session_service.upload_note(file, session, objects, notes)
    assert exc.value.status_code == 400
    objects.put.assert_not_awaited()
    notes.save_note.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_note_persists_metadata_and_uploads_file(session: Session):
    file = _make_upload_file("note.pdf", "application/pdf", b"%PDF content")
    objects, notes = AsyncMock(), AsyncMock()
    notes.count_notes.return_value = 0
    result = await session_service.upload_note(file, session, objects, notes)
    assert result == {"status": "uploaded"}
    metadata = notes.save_note.call_args.kwargs
    objects.put.assert_awaited_once_with(
        "session-pdfs", f"{session.user_id}/{session.id}/{metadata['storage_key']}",
        b"%PDF content", content_type="application/pdf",
    )
    assert metadata['session_id'] == session.id
    assert metadata['user_id'] == session.user_id
    assert metadata['filename'] == "note.pdf"


@pytest.mark.asyncio
async def test_end_session_marks_db_and_cleans_storage(session: Session):
    sessions, notes, objects = AsyncMock(), AsyncMock(), AsyncMock()
    with patch("app.utils.storage_helper.cleanup_storage", new=AsyncMock()) as cleanup:
        result = await session_service.end_session(session, objects, sessions, notes)
    assert result["session_id"] == str(session.id)
    sessions.end_session.assert_awaited_once_with(session_id=session.id, user_id=session.user_id)
    cleanup.assert_not_awaited()



@pytest.mark.asyncio
async def test_upload_failure_does_not_create_broken_note_metadata(session: Session):
    file = _make_upload_file("note.pdf", "application/pdf", b"%PDF content")
    objects, notes = AsyncMock(), AsyncMock()
    notes.count_notes.return_value = 0
    objects.put.side_effect = RuntimeError("storage down")
    with pytest.raises(HTTPException):
        await session_service.upload_note(file, session, objects, notes)
    notes.save_note.assert_not_awaited()


@pytest.mark.asyncio
async def test_metadata_failure_removes_orphan_upload(session: Session):
    file = _make_upload_file("note.pdf", "application/pdf", b"%PDF content")
    objects, notes = AsyncMock(), AsyncMock()
    notes.count_notes.return_value = 0
    notes.save_note.side_effect = RuntimeError("db down")
    with pytest.raises(HTTPException):
        await session_service.upload_note(file, session, objects, notes)
    objects.put.assert_awaited_once()
    objects.delete.assert_awaited_once_with("session-pdfs", [objects.put.call_args.args[1]])
