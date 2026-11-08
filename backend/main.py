from contextlib import asynccontextmanager

import httpx
from app.providers.factory import build_transcription_provider
from app.providers.guarded import BudgetedTranscriptionProvider
from app.adapters.usage import PostgresTranscriptionBudget
from app.clients.pool import close_pool, create_pool, get_pool
from app.clients.supabase_client import init_supabase_client
from app.core.config import Settings, get_settings
from app.routers import audio_router, capabilities_router, sessions_router, workspace_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    await create_pool(settings.POSTGRES_URL)
    try:
        await init_supabase_client()
        async with httpx.AsyncClient() as client:
            app.state.transcription_provider = BudgetedTranscriptionProvider(
                build_transcription_provider(settings, client),
                PostgresTranscriptionBudget(get_pool(), settings), settings)
            yield
    finally:
        await close_pool()


app = FastAPI(
    title="Context-Aware Lecture Captioning API", version="0.1.0", lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router.router)
app.include_router(workspace_router.router)
app.include_router(audio_router.router)
app.include_router(capabilities_router.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
