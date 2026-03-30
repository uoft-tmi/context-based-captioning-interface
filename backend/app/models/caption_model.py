from pydantic import BaseModel

# --- Response models (corrected) ---


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool


class InitResponse(BaseModel):
    status: str


class NotesResponse(BaseModel):
    status: str


class TranscriptChunk(BaseModel):
    partial_text: str


class FinalTranscript(BaseModel):
    final_transcript: str
