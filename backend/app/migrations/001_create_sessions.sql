CREATE TABLE public.sessions (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    mode                  TEXT NOT NULL CHECK (mode IN ('baseline', 'context')),
    is_active             boolean default true,
    error                 text default null,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at            TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '2 hours' CHECK (expires_at > created_at),
    finalized_at          TIMESTAMPTZ DEFAULT NULL CHECK (finalized_at > created_at),
    transcript_key        text default null
);

create index on sessions (user_id, is_active);

create table public.session_notes (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid references auth.users(id) on delete cascade,
    session_id  uuid references public.sessions(id) on delete cascade,
    filename    text not null,
    storage_key text not null,
    created_at  timestamptz default now(),
    UNIQUE (session_id, filename)
);

create index on session_notes (session_id);

-- Enable RLS
ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.session_notes ENABLE ROW LEVEL SECURITY;

-- Sessions: users can only touch their own
CREATE POLICY "users can access own sessions"
ON public.sessions
FOR ALL
USING (auth.uid() = user_id);

-- Chunks: users can only touch chunks belonging to their sessions
CREATE POLICY "users can access own notes"
ON public.session_notes
FOR ALL
USING (auth.uid() = user_id);