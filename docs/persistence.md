# Object storage and PostgreSQL

Supabase is the initial deployment: Supabase Auth, Supabase Storage, and Supabase-hosted PostgreSQL. Object storage and metadata are separate dependencies; choosing a different PostgreSQL host does not require changing object storage or sign-in.

## Interfaces

[Persistence contracts](../backend/app/ports/persistence.py) are Python `Protocol` interfaces. Services depend on these contracts rather than SDKs, connections, or SQL.

| Contract | Responsibility | Current adapter |
| --- | --- | --- |
| `ObjectStore` | Put, get, and delete bytes in a bucket; ensure a private bucket exists | `SupabaseObjectStore` |
| `SessionRepository` | Session creation/history/ownership, transcript keys, atomic stream leases | `PostgresSessionRepository` |
| `NotesRepository` | Note filenames and storage keys | `PostgresNotesRepository` |

The session repository extends the streaming contract, so REST and WebSocket operations use the same persistence implementation. Uniqueness failures become `PersistenceConflictError` in the SQL adapters and HTTP 409 in the service. Stream claims and lease renewals retain their existing atomic SQL behavior.

[StoredCaptionStore](../backend/app/adapters/caption_store.py) composes these interfaces: it downloads notes from the object store and renders/uploads transcript PDFs before publishing their keys in the session repository. Notes upload and download, transcript download, and cleanup use the same object-store dependency.

Object-store keys are relative to their bucket. `put` overwrites an existing key, `get` returns bytes, and `delete` tolerates missing keys. Failures raise exceptions. Uploading a note happens before inserting metadata; a metadata failure triggers deletion of the uploaded object. Files are retained after finalization; explicit cleanup deletes metadata only after object deletion succeeds. SQL and object storage do not share a transaction; failed compensation can leave an orphan object, which is logged.

## Supabase setup now

Existing backend configuration remains valid; no new provider setting is required:

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SECRET_KEY=sb_secret_your-backend-key
POSTGRES_URL=your-supabase-postgresql-connection-string
```

Keep the existing `SUPABASE_JWKS_URL` and frontend authentication settings. Apply the top-level Supabase migrations 001–006 as described in the README. Create a private `session-pdfs` bucket; `transcripts` is created privately on the first save if necessary. Existing object paths and database records remain compatible.

## Change the PostgreSQL host

The SQL adapter uses `asyncpg` and ordinary PostgreSQL. Supabase, Neon, and local PostgreSQL use the same implementation; there is no vendor-specific database SDK.

1. For a **fresh standalone database**, run [postgres/001_create_tables.sql](../backend/app/migrations/postgres/001_create_tables.sql). Follow it with the top-level `006_dashboard_library.sql` migration. Together they provide session names, stored transcripts, plans, recording allowances, notes, indexes, and lease fields without requiring Supabase auth tables.
2. Set `POSTGRES_URL` to the new host's connection string, including its required TLS options, and restart the backend. Use a connection endpoint compatible with `asyncpg` and the configured pool limits. Prepared-statement caching is already disabled for pooler compatibility.
3. Leave Supabase Storage and Auth settings as they are if you still use those services.

The standalone schema is for backend access: ownership checks happen in repository queries. It does not install Supabase RLS policies or delete records automatically when a Supabase Auth user is removed. The top-level Supabase migrations retain those integrations. Do not run both schema bootstraps on the same database. An existing deployment needs its data copied with IDs and object keys preserved; changing the connection string alone does not move records. No existing database is migrated automatically.

## Change the object store

The production object-store adapter currently implemented is **Supabase Storage**. R2 and Backblaze B2 are extension targets, not installed adapters.

To introduce either, implement `ObjectStore` using its S3-compatible API. Keep the logical bucket names `session-pdfs` and `transcripts`, or map them to configured physical buckets inside the adapter. Keep keys unchanged when copying existing files. If buckets must be provisioned separately, `ensure_bucket` should verify their existence and propagate errors.

Wire the adapter in [get_object_store](../backend/app/core/dependencies.py) and replace the Supabase storage-client initialization in [main.py](../backend/main.py) with the new client's startup/shutdown lifecycle. No service or route needs to change. Supabase Auth stays independent; replacing storage does not require replacing sign-in.

To introduce a non-PostgreSQL database later, implement `SessionRepository` and `NotesRepository` and replace their dependency factories. Stream claim/refresh/finish must remain atomic across workers; an in-process lock alone is insufficient.

## Tests without cloud services

FastAPI dependency overrides can replace the stores independently:

```python
from app.core.dependencies import (
    get_object_store, get_session_repository, get_notes_repository,
)

app.dependency_overrides[get_object_store] = lambda: memory_objects
app.dependency_overrides[get_session_repository] = lambda: memory_sessions
app.dependency_overrides[get_notes_repository] = lambda: memory_notes
```

[Persistence port tests](../backend/tests/test_persistence_ports.py) exercise the real REST routes and streaming transcript finalization with these replacements. [Adapter tests](../backend/tests/adapters/test_persistence.py) check Supabase SDK translation and database conflict translation without live credentials.

From `backend/`:

```bash
python -m pytest -q
```

With `TEST_DATABASE_URL` set to a local PostgreSQL admin connection, the integration suite creates disposable databases and runs against both schema bootstraps. These tests exercise real SQL and WebSockets with simulated model and object-store responses. They do not establish live Supabase Storage connectivity.
