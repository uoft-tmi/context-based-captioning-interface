from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.clients.caption_model_client import ModelClient
from app.clients.pool import close_pool, create_pool
from app.clients.supabase_client import init_supabase_client
from app.core.config import Settings, get_settings
from app.routers import audio_router, sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    await create_pool(settings.POSTGRES_URL)
    await init_supabase_client()
    async with httpx.AsyncClient(base_url=settings.MODEL_BASE_URL) as client:
        app.state.model_client = ModelClient(client)
        yield
    await close_pool()


app = FastAPI(
    title="Context-Aware Lecture Captioning API", version="0.1.0", lifespan=lifespan
)


origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router.router)
app.include_router(audio_router.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
