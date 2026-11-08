# Context-Aware Lecture Captioning

Live captions for lectures, with optional PDF notes to help the model understand course terminology. When a recording ends, you can read the transcript and download it as a PDF.

The app uses a **Next.js frontend**, a **FastAPI backend**, and **Supabase** for sign-in, PostgreSQL, and file storage by default. Storage and database access use separate interfaces so they can be changed independently. Groq handles transcription by default; a separate model server is optional.

## What you need

- Node.js 22.13 or newer
- Python 3.11 or newer
- A Supabase project
- A transcription provider: Groq, your own model server, or the mock provider for tests

## Choose a transcription provider

Set `TRANSCRIPTION_PROVIDER` in `backend/.env`, then restart the backend.

| Value | Use it for | API key needed? |
| --- | --- | --- |
| `groq` | Real speech recognition using Groq's free-tier Whisper API | Yes: `GROQ_API_KEY` |
| `mock` | Repeatable tests with synthetic captions | No |
| `custom` | Your existing model server, including PDF notes | Your model server's credentials |
| `wispr` | Optional Wispr Flow integration with approved API access | Yes: `WISPR_API_KEY` |

For free-tier transcription testing, add these settings to `backend/.env`:

```dotenv
TRANSCRIPTION_PROVIDER=groq
GROQ_API_KEY=your-key-here
```

Create a key in the [Groq console](https://console.groq.com/keys). Keep it on the backend. Groq is the default provider; set `TRANSCRIPTION_PROVIDER=custom` explicitly to use your model server. On a hosting platform, configure `GROQ_API_KEY` in the backend's runtime environment settings and redeploy. Change any existing `TRANSCRIPTION_PROVIDER=custom` setting to `groq`.

Groq sends the first second of audio for an earlier first caption, then uses 3.2-second chunks with request pacing to stay within its published free-tier request limit for one continuous recording (including a final partial chunk). Limits apply across your account, so use `mock` for high-concurrency tests. Groq, Wispr, and mock currently support **audio-only baseline mode**; the UI disables PDF mode for them.

**Wispr is optional, not a verified free API.** Its official documentation requires [approved access](https://api-docs.wisprflow.ai/quickstart) and describes [usage-based billing](https://api-docs.wisprflow.ai/usage_billing).

To test one provider without a database, sign-in, or web server, run this from `backend/` with the virtual environment active:

```bash
python -m benchmarks.transcribe_audio --provider groq --audio /tmp/lecture-chunk.wav
```

Use a short **16 kHz, mono, PCM16 WAV** file. Replace `groq` with `mock` to check the wiring without API access; mock output is synthetic. See [provider setup and dependency interfaces](docs/providers.md) for details.

## Set up the database

SQL files are in [backend/app/migrations](backend/app/migrations). For Supabase, use the top-level migrations below. For a fresh standalone PostgreSQL database such as Neon, run [postgres/001_create_tables.sql](backend/app/migrations/postgres/001_create_tables.sql) followed by [006_dashboard_library.sql](backend/app/migrations/006_dashboard_library.sql) and [007_provider_usage.sql](backend/app/migrations/007_provider_usage.sql); these have no dependency on Supabase auth tables. See [persistence interfaces and switching providers](docs/persistence.md).

| Your database | What to run |
| --- | --- |
| New Supabase project | Run migrations **001 through 007**, in order. |
| Existing project with migration 001 already applied | Run the updated **003**, **004**, **005**, **006**, and **007**, in that order. If 003-006 are already applied, run only **007**. |

You can run each file in the Supabase SQL editor. Stop recording sessions before upgrading an existing database.

Migration 003 closes expired sessions and keeps the newest session if a user has multiple active sessions. Migration 005 adds the fields needed to prevent two connections from streaming into the same session.

**Scheduled cleanup is optional.** Migration 002 only schedules cleanup if `pg_cron` is already enabled in Supabase. The app also checks for expired sessions itself.

In Supabase Storage, create a **private** bucket named `session-pdfs` for uploaded notes. The backend creates the private `transcripts` bucket when it first saves a transcript, provided its backend secret key has permission.

## Run the backend

For deployment, see [private-demo Docker setup and usage controls](docs/deployment.md). Demo mode defaults to allowing only Supabase user ID `73abb4e6-38fc-4e6f-a706-aad1e8ad4bc9`, configured through `DEMO_ALLOWED_USER_ID`. Apply migration **007** before deploying this release; shared provider usage limits survive session deletion and server restarts.

Open a terminal at the repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

Edit `backend/.env` and fill in these values:

| Variable | Value to provide |
| --- | --- |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SECRET_KEY` | Your Supabase secret key (`sb_secret_...`); keep it on the backend |
| `SUPABASE_JWKS_URL` | Your project's JWKS URL for verifying sign-in tokens |
| `POSTGRES_URL` | Your Supabase PostgreSQL connection string (or another PostgreSQL host) |
| `TRANSCRIPTION_PROVIDER` | `groq`, `mock`, `custom`, or `wispr` |
| `GROQ_API_KEY` | Your Groq key when using `groq` |

For `custom`, also set `MODEL_BASE_URL` and `MODEL_API_KEY`. For `mock`, no transcription key is needed. The full web app still needs Supabase and PostgreSQL with every provider.

Leave the other settings at their defaults to start. The backend currently expects Supabase tokens signed with ES256.

Then, in the same terminal:

```bash
uvicorn main:app --reload
```

The backend runs at **http://localhost:8000**. You can browse its HTTP API at **http://localhost:8000/docs**.

## Run the frontend

Open a **second terminal** at the repository root:

```bash
cd frontend
npm ci
cp .env.local.example .env.local
```

Edit `frontend/.env.local`:

| Variable | Value to provide |
| --- | --- |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Your Supabase publishable key (`sb_publishable_...`) |
| `NEXT_PUBLIC_BACKEND_BASE_URL` | `http://localhost:8000` for local development |

Next.js explicitly exposes only `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` to the browser through `next.config.ts`. Keep `SUPABASE_SECRET_KEY` and `SUPABASE_JWKS_URL` in the backend configuration. Restart development servers or rebuild after changing frontend values. Legacy frontend key variable names remain supported as fallbacks.

Then, in that terminal:

```bash
npm run dev
```

Open **http://localhost:3000**.

## Use the app

1. Sign in to open the **Dashboard**, which lists active and past sessions.
2. Select **Create session**, provide a unique name, and choose a captioning mode.
3. Open **Session details** to upload optional PDF files and review the recording allowance.
4. Continue to **Recording**, start your microphone, and watch captions appear.
5. Stop recording, or let the recording allowance end it automatically. The **Transcript** page displays the saved text and a formatted PDF download.

Free users can record **30 seconds per session**. Paid status is administrator-managed; paid users get `MAX_SESSION_DURATION_SECONDS` (one hour by default). Only one session can be active per user. Preparation does not consume recording allowance.

Sessions, transcripts, and uploaded files remain available until explicit deletion. The **File library** groups uploaded PDFs by session. See [workspace setup, retention, and paid-plan administration](docs/workspace.md).

## Run the tests

### Frontend

From `frontend/`:

```bash
npm test
npm run lint
npx tsc --noEmit
npm run build
```

These checks cover the streaming message flow, type checking, code quality, and the production build.

### Backend

From `backend/`, with the virtual environment active:

```bash
python -m pytest -q
```

Unit tests run without external services. They include REST notes operations and streaming transcript saving with replacement object stores and repositories. PostgreSQL integration tests are skipped unless you set `TEST_DATABASE_URL`; when enabled, they run against both the Supabase-compatible and standalone PostgreSQL schemas.

To include the integration tests, start a local PostgreSQL server and run:

```bash
TEST_DATABASE_URL=postgresql://localhost/postgres python -m pytest -q -s
```

Replace the connection string if your local server uses a different user, password, or port. The database user must be allowed to create databases. Each test creates and removes its own temporary database.

Backend tests disable dotenv loading and use synthetic settings. The backend also has isolated streaming tests that replace transcription, caption storage, session state, and token verification through interfaces. These run without PostgreSQL or Supabase.

The integration tests use **real PostgreSQL and WebSocket connections**, with simulated authentication, file storage, and model responses. They check session ownership, duplicate connections, expiry, notes uploads, failure handling, and transcript downloads.

## Test concurrent sessions and latency

The latency test checks whether the backend can handle **N sessions at once** while keeping **p95 chunk-to-transcript latency below X milliseconds**.

For example, a 500 ms p95 budget means at least 95% of audio chunks must receive their matching captions within 500 ms of being sent. This measurement excludes the time spent collecting microphone audio, starting the session, and saving the final transcript.

From `backend/`, with the virtual environment active and local PostgreSQL running:

```bash
TEST_DATABASE_URL=postgresql://localhost/postgres \
LATENCY_SESSIONS=20 \
LATENCY_P95_MS=500 \
python -m pytest -m latency -q -s
```

Change these settings to choose your workload:

| Setting | Default | Meaning |
| --- | --- | --- |
| `LATENCY_SESSIONS` | `20` | Number of simultaneous sessions |
| `LATENCY_P95_MS` | `500` | Maximum allowed p95 latency, in milliseconds |
| `LATENCY_CHUNKS` | `10` | Audio chunks sent per session |
| `LATENCY_INTERVAL_MS` | `30` | Time between chunks, in milliseconds |
| `LATENCY_MODEL_DELAY_MS` | `20` | Simulated model response time, in milliseconds |

The test fails if the p95 budget is exceeded, responses are missing or out of order, or a session fails. It also checks that every session finishes without leaving an active session behind.

**This is a backend regression test.** Its simulated model response does not measure real GPU inference speed or transcription accuracy.

### Measure latency with the real model

Use the load-test script against a running backend to include real model response times. High-concurrency runs can exceed a hosted provider's free quota; start with one session when testing Groq. You need:

- One valid Supabase access token per test user, saved as a JSON array in a file outside this repository. Each token must belong to a different user without an active session.
- A representative audio chunk in **16 kHz, mono, PCM16 WAV** format.

From `backend/`, with the virtual environment active:

```bash
python -m benchmarks.stream_latency \
  --base-url http://localhost:8000 \
  --tokens-file /tmp/caption-test-tokens.json \
  --audio /tmp/lecture-chunk.wav \
  --sessions 20 \
  --chunks 10 \
  --interval-ms 2500 \
  --p95-ms 2000 \
  --output /tmp/caption-latency.json
```

Replace the URL and file paths as needed. The script creates and ends baseline sessions for those users.

The report includes p50, p95, p99, maximum latency, finalization time, and any failures. The command exits with an error if the run is incomplete or exceeds your p95 budget. The example's **2000 ms** budget is a threshold you choose, not a measured performance claim.

## Operational notes

- A recording waits for the model and uploaded notes to be ready before sending microphone audio.
- Stopping waits for the final audio and transcript to be saved before showing the download button.
- A crashed streaming worker requires a new session; resuming the old recording is not supported.
- Database pool limits apply to each backend process. Set `DB_POOL_MAX_SIZE` with your total worker count and PostgreSQL connection limit in mind.
- WebSocket authentication uses a token in the connection URL. Redact query strings in server and proxy logs so tokens are not recorded.
