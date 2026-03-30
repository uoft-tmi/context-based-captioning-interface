from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_JWKS_URL: str = ""
    SUPABASE_AUDIENCE: str = ""
    POSTGRES_URL: str = ""

    # Limits
    MAX_SESSION_DURATION_SECONDS: int = 3600  # 1 hour
    SESSION_TIMEOUT_SECONDS: int = 30
    EXPIRY_SLIDE_SECONDS: int = 30
    MAX_PDF_SIZE: int = 10 * 1024 * 1024  # 10 MB
    MAX_NOTES_PER_SESSION: int = 3
    CHUNK_TIMEOUT_SECONDS: int = 15
    NOTES_TIMEOUT_SECONDS: int = 60

    # Model API
    MODEL_BASE_URL: str = ""
    MODEL_API_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
