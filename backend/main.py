from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.database.pool import close_pool, create_pool
from app.database.supabase_client import init_supabase_client
from app.routers import sessions_router, stream_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    await create_pool(settings.POSTGRES_URL)
    await init_supabase_client()
    yield
    await close_pool()


app = FastAPI(
    title="Context-Aware Lecture Captioning API", version="0.1.0", lifespan=lifespan
)

origins = ["https://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router.router, prefix="api")
app.include_router(stream_router.router, prefix="ws")


@app.get("/health")
async def health():
    return {"status": "ok"}
