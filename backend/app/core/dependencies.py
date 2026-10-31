from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection
from supabase import AsyncClient

from app.adapters.caption_store import StoredCaptionStore
from app.adapters.object_store import SupabaseObjectStore
from app.adapters.repositories import PostgresNotesRepository, PostgresSessionRepository
from app.clients.supabase_client import get_supabase_client
from app.core.db_dependencies import DBPool
from app.ports.captioning import CaptionStore, StreamSessionRepository, TranscriptionProvider
from app.ports.persistence import NotesRepository, ObjectStore, SessionRepository
from app.services.caption_model_service import CaptionModelService


def get_transcription_provider(connection: HTTPConnection) -> TranscriptionProvider:
    return connection.app.state.transcription_provider


def get_object_store(supabase: AsyncClient = Depends(get_supabase_client)) -> ObjectStore:
    # Add another adapter here when introducing an S3-compatible provider.
    return SupabaseObjectStore(supabase)


def get_session_repository(db: DBPool) -> SessionRepository:
    return PostgresSessionRepository(db)


def get_notes_repository(db: DBPool) -> NotesRepository:
    return PostgresNotesRepository(db)


Objects = Annotated[ObjectStore, Depends(get_object_store)]
Sessions = Annotated[SessionRepository, Depends(get_session_repository)]
Notes = Annotated[NotesRepository, Depends(get_notes_repository)]


def get_caption_store(sessions: Sessions, notes: Notes, objects: Objects) -> CaptionStore:
    return StoredCaptionStore(sessions, notes, objects)


def get_stream_sessions(sessions: Sessions) -> StreamSessionRepository:
    return sessions


def get_caption_service(
    provider: TranscriptionProvider = Depends(get_transcription_provider),
    store: CaptionStore = Depends(get_caption_store),
) -> CaptionModelService:
    return CaptionModelService(provider, store)
