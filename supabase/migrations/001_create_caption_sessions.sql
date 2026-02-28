-- Create caption_sessions table
CREATE TABLE caption_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    mode TEXT NOT NULL CHECK (mode IN ('baseline', 'context')),
    status TEXT NOT NULL DEFAULT 'init' CHECK (status IN ('init', 'notes_processing', 'ready', 'streaming', 'finalizing', 'complete', 'error')),
    notes_storage_path TEXT,
    transcript_storage_path TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    error_code TEXT,
    error_message TEXT
);

-- Index for fast user lookups
CREATE INDEX idx_caption_sessions_user_id ON caption_sessions(user_id);

-- Enable Row Level Security
ALTER TABLE caption_sessions ENABLE ROW LEVEL SECURITY;

-- Users can only see their own sessions
CREATE POLICY "Users can view own sessions"
    ON caption_sessions FOR SELECT
    USING (auth.uid() = user_id);

-- Users can create sessions for themselves
CREATE POLICY "Users can create own sessions"
    ON caption_sessions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own sessions
CREATE POLICY "Users can update own sessions"
    ON caption_sessions FOR UPDATE
    USING (auth.uid() = user_id);
