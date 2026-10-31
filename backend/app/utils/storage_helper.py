import logging
from typing import Optional
from uuid import UUID

from app.ports.persistence import NotesRepository, ObjectStore

logger = logging.getLogger(__name__)


async def cleanup_storage(
    user_id: UUID,
    notes: NotesRepository,
    objects: ObjectStore,
    session_id: Optional[UUID] = None,
) -> None:
    """
    Deletes note PDFs associated with the session from object storage.
    Skips deletion if session_id is not provided.
    """
    if not session_id:
        logger.warning(
            "cleanup_storage called without session_id; skipping bulk delete for user %s",
            user_id,
        )
        return

    bucket = "session-pdfs"
    storage_keys = await notes.list_note_storage_keys(
        session_id=session_id,
        user_id=user_id,
    )
    file_paths = [f"{user_id}/{session_id}/{key}" for key in storage_keys]
    if not file_paths:
        return

    try:
        await objects.delete(bucket, file_paths)
        await notes.delete_all_notes(
            session_id=session_id,
            user_id=user_id,
        )
    except Exception as e:
        logger.exception("Error deleting files from storage: %s", e)
