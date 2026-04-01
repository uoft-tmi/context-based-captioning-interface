import logging
from typing import Optional
from uuid import UUID

from app.core.db_dependencies import DBPool
from app.database import notes_db
from supabase import AsyncClient

logger = logging.getLogger(__name__)


async def cleanup_storage(
    user_id: UUID,
    db: DBPool,
    supabase_client: AsyncClient,
    session_id: Optional[UUID] = None,
) -> None:
    """
    Deletes note PDFs associated with the session from Supabase storage.
    Skips deletion if session_id is not provided.
    """
    if not session_id:
        logger.warning(
            "cleanup_storage called without session_id; skipping bulk delete for user %s",
            user_id,
        )
        return

    bucket = "session-pdfs"
    storage_keys = await notes_db.list_note_storage_keys(
        db=db,
        session_id=session_id,
        user_id=user_id,
    )
    file_paths = [f"{user_id}/{session_id}/{key}" for key in storage_keys]
    if not file_paths:
        return

    try:
        await supabase_client.storage.from_(bucket).remove(file_paths)
        await notes_db.delete_all_notes(
            db=db,
            session_id=session_id,
            user_id=user_id,
        )
    except Exception as e:
        logger.exception("Error deleting files from storage: %s", e)
