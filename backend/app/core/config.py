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
    MAX_PDF_SIZE: int = 10 * 1024 * 1024  # 10 MB
    MAX_NOTES_PER_SESSION: int = 3

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
