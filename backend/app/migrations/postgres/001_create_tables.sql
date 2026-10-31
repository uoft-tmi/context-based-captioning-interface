-- Fresh standalone PostgreSQL databases (Neon, local PostgreSQL, etc.) only.
-- Supabase projects should continue using the top-level migrations 001-006.
-- Standalone databases: follow this bootstrap with ../006_dashboard_library.sql.
-- Users are authenticated by the backend; no Supabase auth schema is required.
CREATE TABLE public.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('baseline', 'context')),
    is_active BOOLEAN DEFAULT TRUE,
    error TEXT DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '2 hours'
        CHECK (expires_at > created_at),
    finalized_at TIMESTAMPTZ DEFAULT NULL CHECK (finalized_at > created_at),
    transcript_key TEXT DEFAULT NULL,
    stream_id UUID,
    stream_lease_expires_at TIMESTAMPTZ
);

CREATE INDEX ON public.sessions (user_id, is_active);
CREATE UNIQUE INDEX one_active_session_per_user ON public.sessions (user_id)
    WHERE is_active = TRUE;
CREATE INDEX sessions_active_expiry_idx ON public.sessions (expires_at)
    WHERE is_active = TRUE;
CREATE INDEX sessions_user_history_idx ON public.sessions (user_id, created_at DESC);

CREATE TABLE public.session_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    session_id UUID REFERENCES public.sessions(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (session_id, filename)
);
CREATE INDEX ON public.session_notes (session_id);

-- Backend-only connection: ownership is enforced by repository queries.
-- Do not expose these tables through a browser-facing database API.
