"""Caption persistence composed from independent metadata and object stores."""
from starlette.concurrency import run_in_threadpool

from app.models.session import Session
from app.ports.persistence import NotesRepository, ObjectStore, SessionRepository
from app.utils.pdf_helper import transcript_to_pdf_bytes, format_transcript


class StoredCaptionStore:
    def __init__(self, sessions: SessionRepository, notes: NotesRepository, objects: ObjectStore):
        self._sessions = sessions
        self._notes = notes
        self._objects = objects

    async def load_notes(self, session: Session) -> list[bytes]:
        keys = await self._notes.list_note_storage_keys(session.id, session.user_id)
        return [await self._objects.get(
            "session-pdfs", f"{session.user_id}/{session.id}/{key}"
        ) for key in keys]

    async def save_transcript(self, session: Session, transcript: str) -> None:
        transcript = format_transcript(transcript)
        # Preserve readable text even when PDF generation or object storage fails.
        await self._sessions.save_transcript_text(session.id, session.user_id, transcript)
        path = f"transcripts/{session.user_id}/{session.id}.pdf"
        pdf = await run_in_threadpool(
            transcript_to_pdf_bytes, transcript, title=session.name, created_at=session.created_at, duration_ms=session.recorded_duration_ms
        )
        await self._objects.ensure_bucket("transcripts")
        await self._objects.put("transcripts", path, pdf, content_type="application/pdf")
        await self._sessions.set_transcript_key(session.id, session.user_id, path, transcript)

    async def cleanup_notes(self, session: Session) -> None:
        # Files remain in the user's library after recording finishes.
        return None
