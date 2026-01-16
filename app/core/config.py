"""Application settings using pydantic-settings."""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    app_name: str = "property-shared-api"
    environment: str = Field("dev", description="Runtime environment label")

    # Networking
    host: str = "0.0.0.0"
    port: int = 8000

    # External services
    openai_api_key: Optional[str] = None
    epc_api_email: Optional[str] = None
    epc_api_key: Optional[str] = None

    # Polite scraping defaults (in-memory; per-process)
    rightmove_delay_seconds: float = Field(0.6, description="Delay between Rightmove requests")
    rightmove_max_concurrency: int = Field(1, description="Max concurrent Rightmove requests")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
