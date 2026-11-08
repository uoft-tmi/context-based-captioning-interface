# Dashboard, saved sessions, and file library

The signed-in landing page is `/session`. It lists every session, including active, completed, failed, and pending-deletion sessions. Search works by session name. A user can have one active session at a time; ended sessions remain in history.

## Flow

1. **Dashboard**: open an existing session, download/read a transcript, delete a session, or create a new one.
2. **Create session**: provide a name and choose captioning mode. Names are normalized for whitespace and are unique per user, ignoring case, across active and historical sessions. A name can be reused after its session is deleted.
3. **Session details**: see recording allowance and upload/download/delete PDF materials. Up to three PDFs of up to 10 MB each are supported. Files can be kept for reference even when the current provider does not use PDF context.
4. **Recording**: captions stream as before. Recording automatically stops at the account's allowance and saves the transcript.
5. **Transcript**: read a paragraph-formatted transcript and download a PDF with the session name, creation date, recording duration, running header, and page numbers.

Dashboard responses include transcript availability without loading the full text of every past lecture; opening a transcript fetches its text separately.

The **File library** tab groups all remaining uploaded files by session, including ended sessions. Authentication and ownership checks apply to all reads, downloads, and deletions.

## Apply the migration

For an existing Supabase project with migrations 001-005 installed, run `backend/app/migrations/006_dashboard_library.sql` then `007_provider_usage.sql` in the SQL editor. If 006 is already installed, apply only 007. For a new Supabase project, run top-level migrations 001-007 in order.

For a fresh standalone PostgreSQL deployment, run `backend/app/migrations/postgres/001_create_tables.sql` followed by `backend/app/migrations/006_dashboard_library.sql` and `007_provider_usage.sql`.

Migration 006 preserves existing records and gives old sessions a unique generated name. Old PDF transcripts remain downloadable; only new transcripts have stored text previews. Previously deleted note files cannot be restored by the migration.

## Administrator-managed plans

Users are free by default. The backend uses `public.account_plans`; it does not trust browser-supplied plan fields or editable auth metadata. There is no payment integration or public plan-update endpoint. App paid status does not change the transcription provider's own quotas.

In the Supabase SQL editor, replace the placeholder with the user's ID from Authentication > Users:

```sql
INSERT INTO public.account_plans (user_id, plan)
VALUES ('USER_UUID_FROM_AUTH_USERS', 'paid')
ON CONFLICT (user_id) DO UPDATE SET plan = EXCLUDED.plan;
```

Set the plan to `free` to remove paid access. The next recording claim checks the current administrator-managed plan. The WebSocket readiness acknowledgement sends the enforced limit to the browser.

Free users get **30 seconds of decoded microphone audio per session**. Paid users get `MAX_SESSION_DURATION_SECONDS`, defaulting to **3600 seconds**. Preparation and file uploads do not consume recording allowance. Browser timers stop capture, while backend WAV validation, clipping, and atomic duration accounting independently prevent an API client from exceeding its audio budget. Failed transcription attempts still count as recorded audio. An additional bounded drain window permits the last captured segment to reach the server; it does not increase accepted audio duration.

Migration 006 revokes direct mutation permissions on sessions/notes from Supabase's browser roles, and all access to the plan table from those roles. The app's existing backend database connection and secret storage client perform mutations. The backend database role needs read/write privileges on sessions and notes, and SELECT on account_plans. The Supabase SQL editor/administrator manages plans.

## Retention and deletion

Finishing, ending, failing, or expiring a session does **not** remove its session record, transcript, or uploaded files. Expiry ends activity only. Unstarted sessions expire after 24 hours to release the active-session slot; they remain in history. Saved transcripts are retained until explicit deletion.

Deleting a session first atomically marks it for deletion and prevents a competing recording claim. A healthy recording must be stopped before deletion. Objects are removed before the database record; if object cleanup fails, the record remains visible with retryable deletion status. Retrying is safe for missing objects. The final database deletion cascades note metadata. A note upload racing with session deletion cannot insert metadata into a deleting session and attempts to remove its uploaded object.

Transcript text is committed to PostgreSQL before PDF rendering/upload. If PDF storage fails, the saved text remains accessible in history and a PDF can be generated on demand from that text. Paragraph formatting changes whitespace only; it does not rewrite recognized words. Existing core PDF fonts cover WinAnsi text; unsupported glyphs in PDF exports are replaced, while the web transcript retains original Unicode text.

## Verification

Backend tests use synthetic settings and disable dotenv loading. Integration tests cover both Supabase-compatible and standalone PostgreSQL schemas, unique session names, active-session exclusion, trusted plans, atomic recording budgets, retained files/history, and deletion races. The tests and fixtures are in `backend/tests/`. Frontend protocol, buffer, pacing, and dashboard formatting tests are in `frontend/tests/`.
