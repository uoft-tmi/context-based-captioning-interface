import logging
from uuid import UUID

import asyncpg
from app.clients.caption_model_client import ModelClient
from app.core.db_dependencies import DBPool
from app.core.exceptions import ModelUnavailableError
from app.database import notes_db, sessions_db
from app.models.session import Session
from app.utils.pdf_helper import transcript_to_pdf_bytes
from app.utils.storage_helper import cleanup_storage
from supabase import AsyncClient

logger = logging.getLogger(__name__)
TRANSCRIPTS_BUCKET = "transcripts"
TRANSCRIPTS_MIME_TYPES = ["application/pdf", "text/plain"]


class CaptionModelService:
    def __init__(self, client: ModelClient):
        self._client = client

    async def start_session(self, session: Session) -> None:
        """Call model server to allocate session context."""
        await self._client.init_session(
            session_id=session.id,
            mode=session.mode,
        )

    async def upload_notes(
        self,
        session: Session,
        db: DBPool,
        supabase: AsyncClient,
    ) -> None:
        """Fetch all session note PDFs from Supabase storage and send to model server."""
        if session.mode != "context":
            return

        storage_keys = await notes_db.list_note_storage_keys(
            db=db,
            session_id=session.id,
            user_id=session.user_id,
        )
        for storage_key in storage_keys:
            pdf_bytes = await self._fetch_pdf(
                supabase=supabase,
                user_id=session.user_id,
                session_id=session.id,
                storage_key=storage_key,
            )
            await self._client.process_notes(
                session_id=session.id,
                pdf_bytes=pdf_bytes,
            )

    async def transcribe(
        self,
        session: Session,
        audio_chunk: bytes,
        chunk_index: int,
    ) -> str:
        """Transcribe a single audio chunk, returns plain text."""
        result = await self._client.transcribe_chunk(
            session_id=session.id,
            audio=audio_chunk,
            chunk_index=chunk_index,
            mode=session.mode,
        )
        return result.partial_text

    async def finalize(
        self,
        session: Session,
        transcript_chunks: list[str],
        db: asyncpg.Pool,
        supabase: AsyncClient,
    ) -> str:
        """
        Finalize model session, persist transcript to Supabase storage,
        and clean up model server session memory.
        """
        try:
            result = await self._client.finalize(session_id=session.id)
            transcript = result.final_transcript
        except ModelUnavailableError:
            # Model server unreachable — fall back to locally accumulated chunks
            logger.warning(
                "Model server unreachable during finalize for session %s, using local chunks",
                session.id,
            )
            transcript = " ".join(transcript_chunks)

        try:
            await self._persist_transcript(
                session=session,
                transcript=transcript,
                db=db,
                supabase=supabase,
            )
        except Exception:
            # Keep stream completion resilient even if storage is misconfigured.
            logger.exception("Failed to persist transcript for session %s", session.id)

        return transcript

    async def end_session_and_cleanup(
        self,
        session: Session,
        db: DBPool,
        supabase: AsyncClient,
    ) -> None:
        """Mark session ended in Postgres and remove session note files from Supabase."""
        await sessions_db.end_session(
            db=db,
            session_id=session.id,
            user_id=session.user_id,
        )
        await cleanup_storage(
            user_id=session.user_id,
            session_id=session.id,
            db=db,
            supabase_client=supabase,
        )

    # --- Private helpers ---

    async def _fetch_pdf(
        self,
        supabase: AsyncClient,
        user_id: UUID,
        session_id: UUID,
        storage_key: str,
    ) -> bytes:
        path = f"{user_id}/{session_id}/{storage_key}"
        response = await supabase.storage.from_("session-pdfs").download(path)
        return response

    async def _persist_transcript(
        self,
        session: Session,
        transcript: str,
        db: asyncpg.Pool,
        supabase: AsyncClient,
    ) -> None:
        path = f"transcripts/{session.user_id}/{session.id}.pdf"
        pdf_bytes = transcript_to_pdf_bytes(
            transcript, title=f"Session {session.id} Transcript"
        )

        await self._ensure_transcripts_bucket(supabase)

        # Upload to Supabase storage
        await supabase.storage.from_(TRANSCRIPTS_BUCKET).upload(
            path,
            pdf_bytes,
            {"content-type": "application/pdf", "upsert": "true"},
        )

        # Store transcript key for retrieval from storage.
        async with db.acquire() as conn:
            await conn.execute(
                """
                UPDATE sessions
                SET transcript_key = $1
                WHERE id = $2
                """,
                path,
                session.id,
            )

    async def _ensure_transcripts_bucket(self, supabase: AsyncClient) -> None:
        try:
            await supabase.storage.get_bucket(TRANSCRIPTS_BUCKET)
            return
        except Exception:
            logger.info(
                "Transcripts bucket missing or inaccessible, attempting to create it"
            )

        try:
            await supabase.storage.create_bucket(
                TRANSCRIPTS_BUCKET,
                options={
                    "public": False,
                    "allowed_mime_types": TRANSCRIPTS_MIME_TYPES,
                },
            )
            return
        except Exception:
            # Handle races where another request created the bucket concurrently.
            await supabase.storage.get_bucket(TRANSCRIPTS_BUCKET)
