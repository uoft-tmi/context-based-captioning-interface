create table public.session_notes (
    id          uuid primary key default gen_random_uuid(),
    session_id  uuid references public.sessions(id) on delete cascade,
    filename    text not null,
    created_at  timestamptz default now()
);