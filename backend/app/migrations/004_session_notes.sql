-- Already created in 001. Safe to apply to a fresh or existing deployment.
create table if not exists public.session_notes (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid references auth.users(id) on delete cascade,
    session_id  uuid references public.sessions(id) on delete cascade,
    filename    text not null,
    storage_key text not null,
    created_at  timestamptz default now(),
    UNIQUE (session_id, filename)
);
