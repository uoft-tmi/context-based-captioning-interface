"""Proxy for interacting with the model."""

import asyncio

from fastapi import WebSocket
from supabase import AsyncClient

from app.core.db_dependencies import DBPool
from app.database import sessions_db
from app.models.session import Session
from app.utils.storage_helper import cleanup_storage


async def _forward_to_model(session: Session, audio_chunk: bytes) -> str:
    # In a real implementation, this would forward the audio chunk to the model
    # and return the generated caption. Here we just return a placeholder.
    await asyncio.sleep(0.5)  # Simulate processing time
    return "Generated caption for the audio chunk"


async def transcribe_chunk(
    session: Session,
    audio_chunk: bytes,
):
    caption = await _forward_to_model(session, audio_chunk)

    return caption


async def finalize(
    websocket: WebSocket,
    session: Session,
    transcript_chunks: list[str],
    db: DBPool,
    supabase_client: AsyncClient,
):
    try:
        # Placeholder for any finalization logic, e.g. saving the transcript, generating a PDF, etc.
        full_transcript = "\n".join(transcript_chunks)

        session_id = str(session.id)
        user_id = str(session.user_id)

        await cleanup_storage(
            user_id=user_id,
            session_id=session_id,
            supabase_client=supabase_client,
            db=db,
        )
        await sessions_db.end_session(db=db, session_id=session_id, user_id=user_id)

        # For example, save the transcript to the database or Supabase storage
        # await save_transcript(session.id, full_transcript, db, supabase)
        await websocket.send_json({"type": "final", "text": full_transcript})
    except Exception as e:
        await websocket.send_json(
            {"type": "error", "text": f"Finalization error: {str(e)}"}
        )
