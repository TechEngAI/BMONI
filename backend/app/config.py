from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_anon_key: str = Field(..., alias="SUPABASE_ANON_KEY")
    supabase_service_key: str = Field(..., alias="SUPABASE_SERVICE_KEY")
    squad_secret_key: str = Field(..., alias="SQUAD_SECRET_KEY")
    squad_public_key: str = Field(..., alias="SQUAD_PUBLIC_KEY")
    squad_merchant_id: str = Field(..., alias="SQUAD_MERCHANT_ID")
    squad_base_url: str = Field("https://sandbox-api-d.squadco.com", alias="SQUAD_BASE_URL")
    squad_callback_url: str = Field(..., alias="SQUAD_CALLBACK_URL")
    squad_webhook_secret: str = Field(..., alias="SQUAD_WEBHOOK_SECRET")
    use_squad_lookup: bool = Field(False, alias="USE_SQUAD_LOOKUP")
    squad_account_lookup_path: str = Field("/account/lookup", alias="SQUAD_ACCOUNT_LOOKUP_PATH")
    bmoni_base_url: str = Field(..., alias="BMONI_BASE_URL")
    bmoni_api_key: str = Field(..., alias="BMONI_API_KEY")
    environment: str = Field("development", alias="ENVIRONMENT")
    frontend_url: str = Field("http://localhost:3000", alias="FRONTEND_URL")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
