# Context-Aware Lecture Captioning

A web app that provides context-aware real-time lecture captioning. Users optionally upload PDF lecture notes before a session, then stream microphone audio to receive near-real-time captions and a downloadable final transcript.

## Architecture

```
[Browser] → [Next.js / Vercel] → [FastAPI / Fly.io] → [Model Server / GPU]
```

- **Frontend:** Next.js (App Router, TypeScript, Tailwind CSS) — deployed on Vercel
- **Backend:** FastAPI — deployed on Fly.io (Docker)
- **Auth + DB + Storage:** Supabase (Auth, Postgres, Storage)
- **Model:** On-demand GPU endpoint (RunPod or equivalent) — owned by model team

The frontend never calls the model server directly. All model access is proxied through the FastAPI backend.

## Repository Structure

```
/
├── frontend/                  # Next.js app
│   ├── app/
│   │   ├── page.tsx           # Login page (Supabase Auth UI)
│   │   └── session/page.tsx   # Session page (record, captions, download)
│   ├── lib/
│   │   ├── supabase.ts        # Supabase browser client
│   │   └── api.ts             # Backend API wrapper
│   └── .env.local.example
├── backend/                   # FastAPI app
│   ├── main.py                # App entrypoint + CORS
│   ├── config.py              # Settings from env vars
│   ├── routers/
│   │   └── sessions.py        # All session endpoints
│   ├── services/
│   │   ├── model_client.py    # Model server HTTP client
│   │   └── supabase_client.py # Supabase admin client
│   ├── middleware/
│   │   └── auth.py            # JWT verification
│   ├── Dockerfile
│   └── .env.example
├── supabase/
│   └── migrations/            # SQL migrations
│       ├── 001_create_caption_sessions.sql
│       └── 002_create_storage_buckets.sql
└── CLAUDE.md                  # Full project spec
```

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11+
- A Supabase project (for auth and database)

### Frontend

```bash
cd frontend
cp .env.local.example .env.local
# Edit .env.local with your Supabase credentials

npm install
npm run dev
```

The frontend runs on [http://localhost:3000](http://localhost:3000).

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your Supabase and model server credentials

uvicorn main:app --reload
```

The backend runs on [http://localhost:8000](http://localhost:8000). API docs are available at [http://localhost:8000/docs](http://localhost:8000/docs).

### Database

Run the SQL migrations in `supabase/migrations/` against your Supabase project (via the SQL editor or Supabase CLI).

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/sessions` | Create session (baseline or context mode) |
| POST | `/api/sessions/{id}/notes` | Upload PDF notes (context mode) |
| POST | `/api/sessions/{id}/start` | Explicitly start session (optional) |
| POST | `/api/sessions/{id}/chunks` | Send audio chunk for transcription |
| POST | `/api/sessions/{id}/stop` | Finalize session, get transcript |
| GET | `/api/sessions/{id}` | Get session status |
| GET | `/api/sessions/{id}/download` | Download transcript |

## How It Works

1. **Sign in** via Supabase Auth (email/password)
2. **Create a session** — choose baseline (audio only) or context mode (with notes)
3. **Upload PDF notes** (context mode only) — backend forwards to model for processing
4. **Record audio** — microphone audio is captured in 3-second chunks, base64-encoded, and sent to the backend
5. **View captions** — the backend proxies each chunk to the model server and returns partial transcription text
6. **Stop & download** — finalize the session to get the full transcript as a downloadable text file

Sessions are limited to 5 minutes max, with 1 active session per user.

## Environment Variables

### Frontend

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon/public key |
| `NEXT_PUBLIC_BACKEND_BASE_URL` | Backend URL (default: `http://localhost:8000`) |

### Backend

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (server-side only) |
| `SUPABASE_JWT_JWKS_URL` | Supabase JWKS URL for JWT verification |
| `MODEL_BASE_URL` | Model server endpoint URL |
| `MODEL_API_KEY` | API key for model server auth |
| `MAX_SESSION_SECONDS` | Max session duration (default: 300) |
| `MAX_CONCURRENT_SESSIONS` | Max concurrent sessions (default: 20) |

## Deployment

**Backend (Fly.io):**
```bash
cd backend
flyctl launch
fly secrets set SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... MODEL_BASE_URL=... MODEL_API_KEY=...
fly deploy
```

**Frontend (Vercel):**
Connect the repo via Vercel Git integration. Set the root directory to `frontend/` and configure environment variables in the Vercel dashboard.

## Current Status

This is the MVP v1 scaffolding. Route handlers return stub responses. See `CLAUDE.md` for the full specification.
