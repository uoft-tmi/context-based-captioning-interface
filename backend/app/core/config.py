from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # The deployed demo is private by default. Match the verified JWT subject.
    DEMO_MODE: bool = True
    DEMO_ALLOWED_USER_ID: UUID = UUID("73abb4e6-38fc-4e6f-a706-aad1e8ad4bc9")
    TRANSCRIPTION_ENABLED: bool = True
    PROVIDER_REQUESTS_PER_MINUTE: int = Field(default=18, ge=1)
    PROVIDER_REQUESTS_PER_DAY: int = Field(default=100, ge=1)
    PROVIDER_REQUESTS_PER_USER_PER_DAY: int = Field(default=50, ge=1)
    PROVIDER_AUDIO_SECONDS_PER_DAY: int = Field(default=1200, ge=1)
    PROVIDER_AUDIO_SECONDS_PER_USER_PER_DAY: int = Field(default=600, ge=1)
    PROVIDER_MIN_CHUNK_INTERVAL_MS: int = Field(default=3500, ge=0, le=60000)
    CORS_ORIGINS: list[str] = ["https://context-based-captioning-interface.vercel.app", "http://localhost:3000"]
    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SECRET_KEY: SecretStr = SecretStr("")
    SUPABASE_JWKS_URL: str = Field(default="", validation_alias=AliasChoices("SUPABASE_JWKS_URL", "SUPABASE_JWT_JWKS_URL"))
    SUPABASE_AUDIENCE: str = "authenticated"
    POSTGRES_URL: str = ""
    DB_POOL_MIN_SIZE: int = Field(default=2, ge=1)
    DB_POOL_MAX_SIZE: int = Field(default=10, ge=1)
    DB_COMMAND_TIMEOUT_SECONDS: float = Field(default=10, gt=0)
    DB_ACQUIRE_TIMEOUT_SECONDS: float = Field(default=10, gt=0)

    # Limits
    MAX_SESSION_DURATION_SECONDS: int = Field(default=3600, gt=0)
    SESSION_TIMEOUT_SECONDS: float = Field(default=30, gt=0)
    STREAM_SETUP_TIMEOUT_SECONDS: float = Field(default=120, gt=0)
    STREAM_FINALIZE_TIMEOUT_SECONDS: float = Field(default=120, gt=0)
    STREAM_LEASE_SECONDS: float = Field(default=180, gt=0)
    MAX_AUDIO_CHUNK_BYTES: int = Field(default=512 * 1024, gt=0)
    MAX_PDF_SIZE: int = 10 * 1024 * 1024  # 10 MB
    MAX_NOTES_PER_SESSION: int = 3
    CHUNK_TIMEOUT_SECONDS: float = Field(default=15, gt=0)
    NOTES_TIMEOUT_SECONDS: int = 60

    # Model API
    MODEL_BASE_URL: str = ""
    MODEL_API_KEY: str = ""

    # Groq is the default; select custom explicitly to use a separate model server.
    TRANSCRIPTION_PROVIDER: Literal["custom", "groq", "wispr", "mock"] = "groq"
    TRANSCRIPTION_LANGUAGE: str = "en"  # empty string enables provider autodetection
    GROQ_API_KEY: SecretStr = SecretStr("")
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_TRANSCRIPTION_MODEL: str = "whisper-large-v3-turbo"
    WISPR_API_KEY: SecretStr = SecretStr("")
    WISPR_BASE_URL: str = "https://platform-api.wisprflow.ai/api/v1/dash"
    MOCK_TRANSCRIPTION_DELAY_MS: float = Field(default=20, ge=0)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_limits(self):
        if "*" in self.CORS_ORIGINS:
            raise ValueError("CORS_ORIGINS must list explicit frontend origins")
        if self.DB_POOL_MIN_SIZE > self.DB_POOL_MAX_SIZE:
            raise ValueError("DB_POOL_MIN_SIZE must not exceed DB_POOL_MAX_SIZE")
        if self.STREAM_LEASE_SECONDS <= max(self.STREAM_SETUP_TIMEOUT_SECONDS, self.STREAM_FINALIZE_TIMEOUT_SECONDS, self.CHUNK_TIMEOUT_SECONDS, self.SESSION_TIMEOUT_SECONDS):
            raise ValueError("STREAM_LEASE_SECONDS must exceed setup, chunk and inactivity timeouts")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
