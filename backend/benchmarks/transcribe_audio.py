"""Test one provider with a WAV file. No PostgreSQL, Supabase, or web server needed."""
import argparse
import asyncio
import io
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import wave

import httpx

from app.core.config import Settings
from app.providers.factory import build_transcription_provider


async def transcribe_file(settings: Settings, audio: bytes) -> dict:
    async with httpx.AsyncClient() as http:
        provider = build_transcription_provider(settings, http)
        session_id = uuid4()
        await provider.start_session(session_id, "baseline")
        started = perf_counter()
        text = await provider.transcribe(session_id, audio, 0, "baseline")
        latency_ms = (perf_counter() - started) * 1000
        transcript = await provider.finalize(session_id, [text])
        return {"provider": provider.capabilities.name, "text": transcript, "latency_ms": round(latency_ms, 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--provider', choices=['custom', 'groq', 'wispr', 'mock'])
    args = parser.parse_args()
    settings = Settings()
    if args.provider:
        settings.TRANSCRIPTION_PROVIDER = args.provider
    audio = args.audio.read_bytes()
    if len(audio) > settings.MAX_AUDIO_CHUNK_BYTES:
        parser.error('Use a short WAV chunk no larger than MAX_AUDIO_CHUNK_BYTES')
    try:
        with wave.open(io.BytesIO(audio)) as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getcomptype()) != (16000, 1, 2, 'NONE'):
                parser.error('Audio must be 16 kHz mono PCM16 WAV')
    except (wave.Error, EOFError):
        parser.error('Audio must be a valid WAV file')
    try:
        print(json.dumps(asyncio.run(transcribe_file(settings, audio)), indent=2))
    except Exception as exc:
        # Provider errors are sanitized; do not dump HTTP requests, headers or API keys.
        from app.core.exceptions import ModelUnavailableError
        if isinstance(exc, (ModelUnavailableError, ValueError)):
            parser.exit(1, f'{exc}\n')
        parser.exit(1, f'Provider test failed ({type(exc).__name__})\n')


if __name__ == '__main__':
    main()
