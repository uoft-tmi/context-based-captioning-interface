from typing import Optional

from supabase import AsyncClient


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

    if session_id:
        path = f"{user_id}/{session_id}"
        files = await supabase_client.storage.from_(bucket).list(path)
        file_paths = [f"{path}/{file['name']}" for file in files if file.get("name")]
        if file_paths:
            await supabase_client.storage.from_(bucket).remove(file_paths)
    else:
        sessions = await supabase_client.storage.from_(bucket).list(user_id)
        for session in sessions:
            session_id = session.get("name")
            if session_id:
                path = f"{user_id}/{session_id}"
                files = await supabase_client.storage.from_(bucket).list(path)
                file_paths = [
                    f"{path}/{file['name']}" for file in files if file.get("name")
                ]
                if file_paths:
                    await supabase_client.storage.from_(bucket).remove(file_paths)
