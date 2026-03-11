from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.database.pool import close_pool, create_pool
from app.routers import sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    await create_pool(settings.POSTGRES_URL)
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

app.include_router(sessions_router.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
