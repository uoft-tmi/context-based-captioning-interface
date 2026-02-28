-- Create storage buckets for notes and transcripts
-- Note: These are executed via Supabase SQL editor or supabase CLI.
-- Storage bucket creation is typically done via the Supabase dashboard
-- or the storage API, but we document the intent here.

INSERT INTO storage.buckets (id, name, public)
VALUES ('notes-pdf', 'notes-pdf', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO storage.buckets (id, name, public)
VALUES ('transcripts', 'transcripts', false)
ON CONFLICT (id) DO NOTHING;

-- Storage policies: backend-mediated only (service role key).
-- No direct client access in MVP — all uploads/downloads go through the FastAPI backend.
