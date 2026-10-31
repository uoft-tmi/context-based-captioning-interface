from dataclasses import asdict

from fastapi import APIRouter, Depends
from app.core.dependencies import get_transcription_provider
from app.ports.captioning import TranscriptionProvider

router = APIRouter(prefix="/api", tags=["configuration"])


@router.get("/capabilities")
def capabilities(provider: TranscriptionProvider = Depends(get_transcription_provider)):
    return asdict(provider.capabilities)
