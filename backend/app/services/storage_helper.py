from supabase import AsyncClient


async def cleanup_storage(user_id: str, supabase_client: AsyncClient) -> None:
    path = f"{user_id}"

    files = await supabase_client.storage.from_("session-pdfs").list(path)
    file_path = [f"{path}/{file['name']}" for file in files if file["name"]]

    await supabase_client.storage.from_("session-pdfs").remove(file_path)
