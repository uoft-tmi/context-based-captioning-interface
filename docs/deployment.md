# Deploy a private captioning demo

The backend Docker image runs the web API. Whisper/GPT-2 inference remains a separate service, or use Groq for the demo. This image does not start a GPU or host the research model.

## Database upgrade

Apply `backend/app/migrations/007_provider_usage.sql` after migration 006 before starting this release. New Supabase databases need migrations 001-007 in order. Standalone PostgreSQL needs `postgres/001_create_tables.sql`, 006, then 007. No live database is migrated automatically during startup.

The backend database role needs SELECT/INSERT on `provider_usage`, usage of its identity sequence, and permission to operate with row-level security enabled (normally the same table-owner/backend role used by the other migrations). Apply the migration as that role. Browser roles cannot access the usage ledger.

## Container settings

On Render (or another Docker host), set the service root/build context to `backend` and Dockerfile path to `Dockerfile`. Build from the repository root with:

```bash
docker build -t lecture-captioning-api ./backend
```

Configure these values in the hosting platform's runtime environment settings:

| Setting | Value |
| --- | --- |
| `SUPABASE_URL` | Your project URL |
| `SUPABASE_SECRET_KEY` | Backend-only Supabase secret key |
| `SUPABASE_JWKS_URL` | Your project's signing-key endpoint |
| `POSTGRES_URL` | PostgreSQL connection URL; use the host-appropriate Supabase pooler with TLS |
| `TRANSCRIPTION_PROVIDER` | `groq` for real audio, `mock` for a no-inference-cost rehearsal, or `custom` for your model server |
| `GROQ_API_KEY` | Required only for Groq; backend only |
| `MODEL_BASE_URL`, `MODEL_API_KEY` | Required for your custom model service |
| `CORS_ORIGINS` | JSON list containing your exact frontend origin, e.g. `["https://your-app.vercel.app"]` |
| `DEMO_MODE` | `true` (default) |
| `DEMO_ALLOWED_EMAIL` | `psjlee42@gmail.com` (default; the only approved account) |
| `TRANSCRIPTION_ENABLED` | `true`; set `false` and restart/redeploy to stop new provider calls |

The entry point listens on `0.0.0.0` and the platform-provided `PORT` (8000 by default), runs one worker, and disables request/WebSocket handshake logs that could expose query tokens. Configure the platform health-check path as `/health`. Preserve WebSocket upgrade support and allow at least several minutes for a recording plus finalization. Set frontend `NEXT_PUBLIC_BACKEND_BASE_URL` to the HTTPS backend URL and rebuild the frontend. Configure Supabase Auth Site URL/redirect URLs for the frontend domain, and sign in with the approved account. Do not expose backend/provider secrets to frontend builds.

The Docker build context permits only requirements, runtime source, and entry-point files. It excludes environment files, virtual environments, tests, and local artifacts. The final image runs as a non-root user. Mounting credential files into the image is unnecessary; inject runtime settings through the host.

## Limits enforced before inference

| Control | Default |
| --- | --- |
| Approved account | Only `psjlee42@gmail.com`, checked from the verified JWT's top-level email claim |
| Recording duration | 30 seconds per session in demo mode, including paid accounts |
| Provider requests across the deployment | 18 per rolling minute, 100 per UTC day |
| Provider requests per user | 50 per UTC day |
| Reserved audio across the deployment | 1,200 seconds per UTC day |
| Reserved audio per user | 600 seconds per UTC day |
| Minimum interval between transcription requests | 3,500 ms; client pacing adds a 200 ms margin |

The corresponding settings are `PROVIDER_REQUESTS_PER_MINUTE`, `PROVIDER_REQUESTS_PER_DAY`, `PROVIDER_REQUESTS_PER_USER_PER_DAY`, `PROVIDER_AUDIO_SECONDS_PER_DAY`, `PROVIDER_AUDIO_SECONDS_PER_USER_PER_DAY`, and `PROVIDER_MIN_CHUNK_INTERVAL_MS`.

Every transcription attempt reserves at least ten seconds of audio allowance, matching [Groq's documented minimum billed file duration](https://console.groq.com/docs/speech-to-text). With these defaults, the 50-call account limit usually stops a demo before its audio limit. Custom model initialization, note processing, and finalization also reserve a provider request. Groq's local start/finalize operations and mock inference do not spend provider-request budget. Automatic custom-model retries are disabled.

Reservations are committed before the provider is called, serialized in PostgreSQL across workers, and retained even when a request fails or a session is deleted. Restarts, deleting history, and creating another account do not reset the shared limits. Missing migrations/database errors deny inference. Requests beyond a limit end recording with a readable message; received caption chunks are still saved when possible. If custom finalization is denied, received chunks become the final transcript without another model call.

Disabling demo mode removes the email restriction and restores normal paid/free recording durations; it does not disable the shared provider budgets. Keep demo mode on for this deployment.

These controls bound application-issued calls and reserved audio. They do not cap a GPU host's model-loading, idle/keep-warm, storage, or other billable resources, nor calls made with the same key outside this app. Set a provider-side spending limit as well. In particular, turn off always-on workers and use scale-to-zero on the model host. The 30-second recording limit alone is not a dollar budget.

## Rehearse before sharing

1. Run the database migration and deploy with `TRANSCRIPTION_PROVIDER=mock`. Confirm `/health`, sign in as the approved account, create a named session, record, and download the saved transcript. Mock captions are synthetic.
2. Switch to `groq` (or the prepared custom endpoint) and restart. Record one short lecture sample; check that captions and the final PDF persist.
3. Sign in with another account: the backend must return 403 and the workspace must display the private-demo access message.
4. Monitor provider usage in the host's console. The server ledger can be inspected with `SELECT action, COUNT(*), SUM(audio_ms) FROM provider_usage WHERE reserved_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' GROUP BY action;`.

Daily allowances reset at midnight UTC. Limit errors describe the wait; do not clear the ledger as a routine workaround. If you deliberately need a larger demo, change the appropriate server-side limits and redeploy.
