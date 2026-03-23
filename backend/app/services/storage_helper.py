from typing import Optional
from uuid import UUID

from supabase import AsyncClient

from app.database import sessions_db


async def cleanup_storage(
    user_id: str,
    supabase_client: AsyncClient,
    session_id: Optional[str] = None,
) -> None:
    """
    Takes in user id and session id and deletes all files in the corresponding storage path in supabase.
    If session id is None, deletes all files in the user's folder.
    """
    bucket = "session-pdfs"

    path = f"{user_id}/{session_id}"
    files = await supabase_client.storage.from_(bucket).list(path)
    file_paths = [f"{path}/{file['name']}" for file in files if file.get("name")]
    if file_paths:
        try:
            await supabase_client.storage.from_(bucket).remove(file_paths)
            await sessions_db.delete_all_notes(
                session_id=UUID(session_id), user_id=UUID(user_id)
            )
        except Exception as e:
            print(f"Error deleting files from storage: {e}")
