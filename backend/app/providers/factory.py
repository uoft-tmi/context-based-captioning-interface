import httpx

from app.clients.caption_model_client import ModelClient
from app.core.config import Settings
from app.ports.captioning import TranscriptionProvider
from app.providers.chunked import GroqWhisperProvider, MockTranscriptionProvider, WisprFlowProvider
from app.providers.custom import CustomModelProvider


def build_transcription_provider(settings: Settings, http: httpx.AsyncClient) -> TranscriptionProvider:
    """Composition root: select concrete adapters once, outside application services."""
    match settings.TRANSCRIPTION_PROVIDER:
        case "custom":
            if not settings.MODEL_BASE_URL:
                raise ValueError("Set MODEL_BASE_URL or choose TRANSCRIPTION_PROVIDER=mock, groq or wispr")
            return CustomModelProvider(ModelClient(http, settings=settings, base_url=settings.MODEL_BASE_URL))
        case "groq":
            return GroqWhisperProvider(http, settings.GROQ_API_KEY.get_secret_value(),
                base_url=settings.GROQ_BASE_URL, model=settings.GROQ_TRANSCRIPTION_MODEL,
                language=settings.TRANSCRIPTION_LANGUAGE, timeout_seconds=settings.CHUNK_TIMEOUT_SECONDS)
        case "wispr":
            return WisprFlowProvider(http, settings.WISPR_API_KEY.get_secret_value(),
                base_url=settings.WISPR_BASE_URL, language=settings.TRANSCRIPTION_LANGUAGE,
                timeout_seconds=settings.CHUNK_TIMEOUT_SECONDS)
        case "mock":
            return MockTranscriptionProvider(delay_ms=settings.MOCK_TRANSCRIPTION_DELAY_MS)
        case _:
            raise ValueError("Unsupported transcription provider")
