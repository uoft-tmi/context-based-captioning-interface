# CLAUDE.md — Context-Aware Lecture Captioning (CBC MVP v1)

## Project Overview

A web app that provides context-aware real-time lecture captioning. Users optionally upload PDF notes before a session, then stream microphone audio in chunks to receive near-real-time captions and a downloadable final transcript.

**Stack:**
- Frontend: Next.js on Vercel
- Backend: FastAPI on Fly.io (Docker)
- Auth + DB: Supabase (Auth + Postgres + Storage)
- Model: On-demand GPU endpoint (RunPod or equivalent) — owned by model team

---

## Architecture

```
[Browser] → [Next.js / Vercel] → [FastAPI / Fly.io] → [Model Server / GPU]
```

**Key rule: The frontend NEVER calls the model server directly. All model access is proxied through the FastAPI backend.**

---

## Repository Structure

```
/
├── frontend/          # Next.js app (Vercel)
│   ├── app/           # App router pages
│   ├── components/    # UI components
│   └── lib/           # Supabase client, API helpers
├── backend/           # FastAPI app (Fly.io)
│   ├── main.py        # App entrypoint
│   ├── routers/       # Route handlers
│   ├── services/      # Model proxy, Supabase client
│   ├── middleware/     # JWT verification
│   └── Dockerfile
└── supabase/
    └── migrations/    # SQL migrations
```

---

## Authentication

- Users authenticate via **Supabase Auth** (email/password or OAuth)
- Frontend attaches the Supabase JWT as `Authorization: Bearer <token>` on every backend request
- Backend verifies the JWT using **Supabase JWKS** and extracts `user_id` from the `sub` claim
- Users can only access their own sessions (`caption_sessions.user_id == sub`)
- Backend authenticates to model server using `Authorization: Bearer <MODEL_API_KEY>` — this key is never exposed to the frontend

---

## Data Model

### `caption_sessions` table (Supabase Postgres)

```sql
id                    UUID PRIMARY KEY
user_id               UUID INDEXED
mode                  TEXT CHECK IN ('baseline', 'context')
status                TEXT CHECK IN ('init', 'notes_processing', 'ready', 'streaming', 'finalizing', 'complete', 'error')
notes_storage_path    TEXT NULL
transcript_storage_path TEXT NULL
started_at            TIMESTAMPTZ NULL
ended_at              TIMESTAMPTZ NULL
created_at            TIMESTAMPTZ DEFAULT now()
error_code            TEXT NULL
error_message         TEXT NULL
```

**RLS:** Users can `SELECT/INSERT/UPDATE` only where `user_id = auth.uid()`.

### Supabase Storage Buckets

- `notes-pdf` (private) — uploaded PDFs
- `transcripts` (private) — final transcript `.txt` files at `transcripts/{user_id}/{session_id}.txt`

Storage access is **backend-mediated only** (no signed URLs in MVP).

---

## Session State Machine

```
INIT
  → NOTES_PROCESSING  (after PDF forwarded to model; context mode only)
  → READY             (model confirms processed, OR user skipped notes)
  → STREAMING         (first chunk accepted; started_at set)
  → FINALIZING        (user hits stop OR 5-min timeout)
  → COMPLETE          (transcript stored and returned)
  → ERROR             (model/validation failure)
  → EXPIRED           (implicit; timed out without finalization)
```

**Duration enforcement:** Backend enforces a hard **5-minute max** from `started_at`. On timeout, backend auto-finalizes and stops accepting new chunks.

**Concurrency:** Max **1 active session per user** at a time.

---

## API Surface

### Frontend → Backend (FastAPI on Fly.io)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/sessions` | Create session (select mode: baseline or context) |
| POST | `/api/sessions/{id}/notes` | Upload PDF notes (multipart, PDF only, max 10MB) |
| POST | `/api/sessions/{id}/start` | Optional; session starts implicitly on first chunk |
| POST | `/api/sessions/{id}/chunks` | Send audio chunk |
| POST | `/api/sessions/{id}/stop` | Finalize session |
| GET | `/api/sessions/{id}` | Get session status + transcript preview |
| GET | `/api/sessions/{id}/download` | Download transcript (optional) |

### Chunk Request/Response

```json
// POST /api/sessions/{id}/chunks
// Request:
{ "chunk_index": 12, "audio_b64": "<base64 wav>", "mime": "audio/wav" }

// Response:
{ "partial_text": "..." }
```

Validation:
- `chunk_index` must be monotonically increasing per session
- Reject if session is not in `ready` or `streaming` state
- Reject if session belongs to a different user

### Backend → Model Server

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/health` | Health check (warm = 200 OK) |
| POST | `/v1/init` | Initialize session context |
| POST | `/v1/process-notes` | Forward PDF for context processing |
| POST | `/v1/transcribe-chunk` | Transcribe audio chunk |
| POST | `/v1/finalize` | Get final transcript |

```json
// POST /v1/transcribe-chunk
// Request:
{ "session_id": "uuid", "chunk_index": 12, "audio_b64": "<base64 wav>", "mode": "baseline" }

// Response:
{ "partial_text": "..." }
```

---

## Audio Chunking

- **Format:** 16kHz mono WAV (or PCM wrapped in WAV)
- **Chunk length:** 3 seconds (tunable)
- **Latency target:** ~2–5 seconds end-to-end
- **Max session:** 5 minutes of audio
- **Capture:** `MediaRecorder` or `WebAudio` API; base64 encode before POST
- **Target browser:** Chrome (Edge/Safari best effort)

### Failure Handling

- If a chunk request to model times out (10s): return partial failure, continue accepting next chunks
- If one chunk fails: retry once
- If retry fails: drop chunk silently, show non-blocking UI warning
- If model server unavailable (503): surface "captioning server starting/unavailable" to user

---

## Notes Upload (Context Mode Only)

- `POST /api/sessions/{id}/notes` — multipart/form-data
- PDF only, max 10MB
- Backend optionally stores PDF in Supabase Storage (`notes-pdf` bucket)
- Backend forwards to model `POST /v1/process-notes` with `session_id` + file
- On success (`{"status": "processed"}`): backend updates session to `ready`

---

## Finalization & Transcript Download

1. Frontend calls `POST /api/sessions/{id}/stop`
2. Backend sets status → `finalizing`, calls model `POST /v1/finalize`
3. Backend receives full transcript text
4. Backend stores transcript at `transcripts/{user_id}/{session_id}.txt` in Supabase Storage
5. Backend sets `transcript_storage_path`, marks session `complete`
6. **MVP download approach (Option A):** Backend returns transcript text in stop response; frontend creates a blob download. Transcript is also persisted in storage.

---

## Environment Variables

### Frontend (Vercel)

```
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
BACKEND_BASE_URL
```

### Backend (Fly.io secrets)

```
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY      # server-side only, never expose to frontend
SUPABASE_JWT_JWKS_URL
MODEL_BASE_URL
MODEL_API_KEY
MAX_SESSION_SECONDS=300
MAX_CONCURRENT_SESSIONS=20
```

### Model Server (GPU provider env)

```
MODEL_API_KEY    # used to verify incoming requests from backend
```

---

## Deployment

### Backend (Fly.io)
```bash
flyctl launch
fly secrets set KEY=value ...
fly deploy
```

- Fly.io handles HTTPS termination
- Ensure CORS allows the Vercel frontend domain
- Use `SUPABASE_SERVICE_ROLE_KEY` only on the backend — never in the frontend

### Frontend (Vercel)
- Standard `next build` / Vercel Git integration
- Set env vars in Vercel project settings

### Model Server
- Dockerized FastAPI deployed to GPU provider (e.g., RunPod)
- Expose HTTPS endpoint to backend only; use IP allowlist if provider supports it, otherwise rely on `MODEL_API_KEY` + rate limits

---

## Abuse Prevention

Enforce server-side in the backend:
- 1 active session per user
- Max 5 minutes per session
- Max ~3 sessions/day per user (optional)
- Chunk rate limit: max 1 chunk/second, average ~1 per 3 seconds

---

## Observability

Backend structured logs must include:
- `session_id`, `user_id`
- Latency per chunk request to model
- Errors and timeouts
- Session duration
- Status transitions

Monitoring: Fly.io logs + GPU provider logs (no dedicated dashboard for MVP).

---

## Security Rules

- Frontend never receives or uses `MODEL_API_KEY` or model endpoint URL
- Validate all uploads: PDF only, max 10MB
- Validate chunk size and posting rate
- Enable Supabase RLS on `caption_sessions`
- Transcripts are private; downloads are backend-mediated

---

## What's Out of Scope (MVP v1)

- Model training or fine-tuning
- Notes parsing / domain term extraction (model team owns this)
- Accuracy metrics or evaluation dashboards
- Scalability beyond ~20 concurrent users
- Session resume after page refresh (deferred)

---

## Definition of Done

- [ ] User can log in via Supabase Auth
- [ ] User can create a session and select mode (baseline or context)
- [ ] User can upload PDF notes or skip
- [ ] Notes processing completes and UI transitions to `ready`
- [ ] Microphone recording works and audio chunks are sent via HTTP
- [ ] Captions appear incrementally in the UI
- [ ] Session auto-stops at 5 minutes
- [ ] User can manually stop and receive final transcript
- [ ] Transcript is downloadable
- [ ] Backend deployed on Fly.io, frontend on Vercel, model endpoint reachable
- [ ] Model server is never called directly from the browser