from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_jwks_url: str = ""
    model_base_url: str = ""
    model_api_key: str = ""
    max_session_seconds: int = 300
    max_concurrent_sessions: int = 20

    model_config = {"env_file": ".env"}


settings = Settings()
