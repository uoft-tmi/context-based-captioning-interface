import base64
import json
from uuid import uuid4

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import ProviderRequestError
from app.ports.captioning import TranscriptionProvider
from app.providers.chunked import GroqWhisperProvider, MockTranscriptionProvider, WisprFlowProvider
from app.providers.factory import build_transcription_provider


async def test_default_provider_sends_groq_multipart_request_and_parses_text(monkeypatch):
    monkeypatch.delenv("TRANSCRIPTION_PROVIDER", raising=False)
    async def handle(request):
        assert str(request.url) == "https://api.groq.com/openai/v1/audio/transcriptions"
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.headers["content-type"].startswith("multipart/form-data;")
        body = await request.aread()
        assert b'name="prompt"' not in body
        assert b'name="file"; filename="chunk-7.wav"' in body
        assert b'Content-Type: audio/wav' in body
        assert b'whisper-large-v3-turbo' in body
        assert b'RIFF audio bytes' in body
        assert b'name="language"' in body and b'en' in body
        return httpx.Response(200, json={"text": "Lecture caption"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        settings = Settings(_env_file=None, GROQ_API_KEY="test-key", MODEL_BASE_URL="")
        provider = build_transcription_provider(settings, http)
        assert isinstance(provider, GroqWhisperProvider)
        assert isinstance(provider, TranscriptionProvider)
        assert await provider.transcribe(uuid4(), b"RIFF audio bytes", 7, "baseline") == "Lecture caption"
        assert provider.capabilities.supports_pdf_notes
        assert provider.capabilities.requires_text_notes
        assert provider.capabilities.recommended_chunk_ms == 3200
        assert provider.capabilities.initial_chunk_ms == 1000
        assert provider.capabilities.min_request_interval_ms == 3200


async def test_wispr_uses_official_rest_schema():
    async def handle(request):
        assert str(request.url) == "https://platform-api.wisprflow.ai/api/v1/dash/api"
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert base64.b64decode(body["audio"]) == b"wav audio"
        assert body["language"] == ["en"]
        assert body["context"]["app"]["type"] == "other"
        return httpx.Response(200, json={"text": "Wispr caption", "detected_language": "en"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        assert await WisprFlowProvider(http, "test-key").transcribe(uuid4(), b"wav audio", 0, "baseline") == "Wispr caption"


@pytest.mark.parametrize('status,retryable,match', [(429, False, "rate limit"), (401, False, "authentication"), (403, False, "authentication"), (503, True, "HTTP 503")])
async def test_provider_failures_are_classified_without_leaking_key(status, retryable, match):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, text="secret-api-key must never appear in a user error")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(ProviderRequestError, match=match) as error:
            await GroqWhisperProvider(http, "secret-api-key").transcribe(uuid4(), b"wav", 0, "baseline")
    assert error.value.retryable is retryable
    assert "secret-api-key" not in str(error.value)
    assert len(calls) == 1  # No hidden retries against a limited free quota.


@pytest.mark.parametrize('payload', [{}, {"text": None}, {"text": 123}, ["invalid"]])
async def test_invalid_provider_response_is_rejected(payload):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as http:
        with pytest.raises(ProviderRequestError, match="invalid"):
            await GroqWhisperProvider(http, "test-key").transcribe(uuid4(), b"wav", 0, "baseline")


async def test_empty_transcript_is_valid_for_silence():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"text": ""}))) as http:
        assert await GroqWhisperProvider(http, "test-key").transcribe(uuid4(), b"wav", 0, "baseline") == ""


async def test_hosted_providers_keep_sessions_separate_and_make_no_finalize_call():
    def no_request(request):
        pytest.fail("Start/finalize must not spend API quota")
    async with httpx.AsyncClient(transport=httpx.MockTransport(no_request)) as http:
        provider = GroqWhisperProvider(http, "test-key")
        first, second = uuid4(), uuid4()
        await provider.start_session(first, "baseline")
        await provider.start_session(second, "baseline")
        assert await provider.finalize(first, ["lecture one"]) == "lecture one"
        assert await provider.finalize(second, ["lecture two"]) == "lecture two"
        with pytest.raises(ValueError, match="baseline"):
            await WisprFlowProvider(http, "test-key").start_session(uuid4(), "context")


@pytest.mark.parametrize('name,expected', [('mock', MockTranscriptionProvider), ('groq', GroqWhisperProvider), ('wispr', WisprFlowProvider)])
async def test_factory_selects_provider_without_touching_storage(name, expected):
    settings = Settings(_env_file=None, TRANSCRIPTION_PROVIDER=name, GROQ_API_KEY="test", WISPR_API_KEY="test")
    async with httpx.AsyncClient() as http:
        provider = build_transcription_provider(settings, http)
        assert isinstance(provider, expected)
        assert isinstance(provider, TranscriptionProvider)


async def test_factory_keeps_custom_model_protocol_and_base_path():
    def handle(request):
        assert str(request.url) == "https://model.test/prefix/v1/transcribe-chunk"
        assert request.headers["authorization"] == "Bearer custom-key"
        assert json.loads(request.content)["chunk_index"] == 0
        return httpx.Response(200, json={"partial_text": "custom caption"})
    settings = Settings(_env_file=None, TRANSCRIPTION_PROVIDER="custom", MODEL_BASE_URL="https://model.test/prefix", MODEL_API_KEY="custom-key")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = build_transcription_provider(settings, http)
        assert provider.capabilities.supports_pdf_notes
        assert await provider.transcribe(uuid4(), b"wav", 0, "baseline") == "custom caption"


@pytest.mark.parametrize('name', ['groq', 'wispr'])
async def test_hosted_provider_requires_key_before_any_requests(name):
    settings = Settings(_env_file=None, TRANSCRIPTION_PROVIDER=name, GROQ_API_KEY="", WISPR_API_KEY="")
    async with httpx.AsyncClient() as http:
        with pytest.raises(ValueError, match="Missing API key"):
            build_transcription_provider(settings, http)


async def test_mock_is_deterministic_without_network():
    provider = MockTranscriptionProvider(delay_ms=0)
    assert await provider.transcribe(uuid4(), b"ignored", 3, "baseline") == "Test caption 3"
    assert await provider.finalize(uuid4(), ["one", "two"]) == "one two"
