import logging
from typing import Optional
from uuid import UUID

from supabase import AsyncClient

from app.core.db_dependencies import DBPool
from app.database import notes_db

logger = logging.getLogger(__name__)


async def cleanup_storage(
    user_id: UUID,
    db: DBPool,
    supabase_client: AsyncClient,
    session_id: Optional[UUID] = None,
) -> None:
    """
    Takes in user id and session id and deletes all files in the corresponding storage path in supabase.
    If session id is None, deletes all files in the user's folder.
    """
    bucket = "session-pdfs"

    path = f"{user_id}/{session_id}" if session_id else f"{user_id}"
    files = await supabase_client.storage.from_(bucket).list(path)
    file_paths = [f"{path}/{file['name']}" for file in files if file.get("name")]
    if file_paths:
        try:
            await supabase_client.storage.from_(bucket).remove(file_paths)
            if session_id:
                await notes_db.delete_all_notes(
                    db=db,
                    session_id=session_id,
                    user_id=user_id,
                )
        except Exception as e:
            logger.exception("Error deleting files from storage: %s", e)
