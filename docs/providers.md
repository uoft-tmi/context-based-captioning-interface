# Transcription providers and modular tests

The browser uses the same backend API regardless of the transcription provider. Choose the provider in `backend/.env` and restart the backend. Provider keys never go to the browser.

## Groq: free-tier Whisper transcription

1. Create an API key at [console.groq.com/keys](https://console.groq.com/keys).
2. Add these settings to `backend/.env`:

   ```dotenv
   TRANSCRIPTION_PROVIDER=groq
   GROQ_API_KEY=your-key-here
   GROQ_TRANSCRIPTION_MODEL=whisper-large-v3-turbo
   TRANSCRIPTION_LANGUAGE=en
   ```

3. Restart the backend and create a **Audio only** session in the UI (baseline mode).

This adapter uploads each WAV chunk to Groq's [documented transcription endpoint](https://console.groq.com/docs/speech-to-text). It joins the successful chunk transcripts when the recording ends. It does not upload PDF notes, call a session-initialization endpoint, or spend another API request on finalization.

Groq currently publishes a 20-request-per-minute limit for this model on its free plan. The browser sends the first second of audio immediately after collecting it, then collects 3.2-second chunks, approximately 19 requests per minute for one continuous recording. Sends are paced at least 3.2 seconds apart so queued audio cannot burst requests after a slow response; stopping can use one additional request for the final partial chunk. Quotas are shared by the organization: overlapping recordings, rapid stop/start cycles, other applications, or account-specific limits can still produce HTTP 429 errors. Check your [account limits](https://console.groq.com/docs/rate-limits).

Groq returns a complete transcription for each uploaded file; this adapter does not receive word-by-word partial results. The first caption requires one second of audio **plus** upload and recognition time, and later captions arrive in phrases based on 3.2-second chunks. Continuous one-second requests would need about 60 requests per minute, above the published free quota. Smaller chunks may reduce recognition context and can split words; live accuracy and latency must be measured with representative speech.

Microphone audio is sent as binary WAV frames over the existing WebSocket, avoiding base64 conversion and its roughly 33% payload expansion. Legacy JSON/base64 input remains accepted by the backend. The browser keeps one acknowledged request in flight and a bounded queue, flushes remaining audio before stopping, and estimates caption delay from the oldest audio sample in a segment through the caption response, including collection and queue time.

A quota or authentication error stops the stream with a readable message. A temporary server or network error warns about the failed chunk and allows later chunks. Requests are not automatically retried against the hosted provider.

## Mock: no transcription account needed

```dotenv
TRANSCRIPTION_PROVIDER=mock
MOCK_TRANSCRIPTION_DELAY_MS=20
```

The mock returns captions such as `Test caption 0`. It does **not** recognize speech. Both session pages display a notice when mock mode is active.

The full app still uses Supabase and PostgreSQL. To test only the provider, use the standalone command below. To test the stream with all external dependencies replaced, run `tests/test_stream_ports.py`.

## Custom: existing model server

```dotenv
TRANSCRIPTION_PROVIDER=custom
MODEL_BASE_URL=https://your-model-server.example
MODEL_API_KEY=your-model-key
```

This remains the default and preserves the existing `/v1/init`, `/v1/process-notes`, `/v1/transcribe-chunk`, and `/v1/finalize` contract. It is currently the only adapter that supports PDF lecture notes.

## Wispr Flow: optional approved API access

Wispr's [quickstart](https://api-docs.wisprflow.ai/quickstart) requires organization approval. Its [billing documentation](https://api-docs.wisprflow.ai/usage_billing) describes usage charges; a free consumer app plan does not establish free API access.

If you already have approved API access:

```dotenv
TRANSCRIPTION_PROVIDER=wispr
WISPR_API_KEY=your-approved-api-key
TRANSCRIPTION_LANGUAGE=en
```

The adapter uses Wispr's [official API-key REST endpoint](https://api-docs.wisprflow.ai/rest_api), with base64 WAV audio and the documented context schema. It sends separate requests for each chunk; it does not implement Wispr's native WebSocket protocol. Wispr can edit and format its output, so its text should not be treated as a verbatim transcription baseline.

PDF notes are not supported by this adapter. API use may incur charges according to your Wispr agreement.

## Test a provider by itself

From `backend/`, with the virtual environment active:

```bash
python -m benchmarks.transcribe_audio \
  --provider mock \
  --audio /tmp/lecture-chunk.wav
```

The input must be a short 16 kHz mono PCM16 WAV file within `MAX_AUDIO_CHUNK_BYTES` (512 KiB by default). The command prints the provider name, resulting text, and the chunk request's latency.

Change `mock` to `groq`, `wispr`, or `custom` to exercise a configured real provider. This command needs no PostgreSQL database, Supabase account, frontend, or running FastAPI server. Real providers still need their own credentials and network access.

## Dependency interfaces

Application contracts live in [captioning.py](../backend/app/ports/captioning.py) and [persistence.py](../backend/app/ports/persistence.py). They are Python `Protocol` interfaces: an implementation supplies the declared methods without needing to inherit a vendor-specific base class.

| Interface | Responsibility | Production implementation |
| --- | --- | --- |
| `TranscriptionProvider` | Start, transcribe, process notes, and finalize | Custom model, Groq, Wispr, or mock |
| `CaptionStore` | Load PDF notes, save a transcript, and clean up notes | `StoredCaptionStore`, composed from repositories and an object store |
| `StreamSessionRepository` | Check ownership and claim, renew, and finish a stream | The PostgreSQL session adapter |
| `TokenVerifier` | Verify a token and return its user ID | `SupabaseTokenVerifier` |
| `SessionRepository` | Create, find, end, and update session metadata | `PostgresSessionRepository` |
| `NotesRepository` | Store and retrieve note metadata | `PostgresNotesRepository` |
| `ObjectStore` | Read, write, and remove file bytes | `SupabaseObjectStore` |

[CaptionModelService](../backend/app/services/caption_model_service.py) depends only on the transcription and caption-store contracts. It has no SQL, HTTP client, or Supabase SDK calls.

The WebSocket route receives session state, caption orchestration, and token verification through FastAPI dependencies. [dependencies.py](../backend/app/core/dependencies.py) constructs the production adapters. [factory.py](../backend/app/providers/factory.py) selects the transcription adapter at startup.

REST session and notes operations also receive repositories and object storage through interfaces. PostgreSQL SQL and Supabase SDK calls remain in their adapters. Replacing those adapters can change the persistence backend without changing session-service logic.

### Replace dependencies in a test

Use `app.dependency_overrides` to supply fakes for:

- `get_transcription_provider`
- `get_caption_store`
- `get_stream_sessions`
- `get_token_verifier`

[The isolated stream tests](../backend/tests/test_stream_ports.py) provide a complete example. They exercise the real WebSocket route, final transcript acknowledgement, failure handling, and ownership checks using in-memory implementations. No database or cloud clients are initialized.

Run the tests from `backend/`:

```bash
python -m pytest tests/providers tests/test_stream_ports.py tests/services/test_caption_model_service.py -q
```

Provider HTTP tests use `httpx.MockTransport` to verify request URLs, authentication, payloads, response parsing, and error handling without spending API quota. They establish adapter compatibility with the documented contract, not a successful live provider call.

### Add another provider

1. Implement `TranscriptionProvider` in `app/providers/`.
2. Declare its capabilities, including whether it accepts PDF notes and its recommended chunk duration.
3. Add a configuration choice and a branch in the provider factory.
4. Add request/response and failure tests.

The streaming service and frontend do not need to know the new provider's HTTP schema. The frontend reads `/api/capabilities` to choose the chunk duration and enable or disable PDF mode.
