CREATE TABLE public.sessions (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    mode                  TEXT NOT NULL CHECK (mode IN ('baseline', 'context')),
    status                TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'finalized', 'error')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW() CHECK (expires_at > created_at),
    expires_at            TIMESTAMPTZ NOT NULL DEFAULT NOW() + Interval '1 hour' CHECK (expires_at > created_at),
    finalized_at          TIMESTAMPTZ DEFAULT NULL CHECK (finalized_at > created_at),
    final_transcript      TEXT
);

CREATE TABLE public.session_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    transcript TEXT NOT NULL,
    model_meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, chunk_index)
);

-- Enable RLS
ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.session_chunks ENABLE ROW LEVEL SECURITY;

-- Sessions: users can only touch their own
CREATE POLICY "users can access own sessions"
ON public.sessions
FOR ALL
USING (auth.uid() = user_id);

-- Chunks: users can only touch chunks belonging to their sessions
CREATE POLICY "users can access own chunks"
ON public.session_chunks
FOR ALL
USING (
    session_id IN (
        SELECT id FROM public.sessions WHERE user_id = auth.uid()
    )
);