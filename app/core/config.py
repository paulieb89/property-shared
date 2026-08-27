"""Application settings using pydantic-settings."""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
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
    epc_api_token: Optional[str] = None  # GOV.UK Bearer token (required for EPC)
    epc_api_email: Optional[str] = None  # deprecated: retired service
    epc_api_key: Optional[str] = None  # deprecated: retired service
    companies_house_api_key: Optional[str] = None
    companies_house_sandbox: bool = False

    # PPD snapshot source. Off by default: with this false the service uses the
    # live adapter exactly as before and DuckDB is never needed.
    ppd_snapshot_enabled: bool = False

    @field_validator("ppd_snapshot_enabled", mode="before")
    @classmethod
    def _parse_snapshot_flag(cls, v):
        """Use property_core's parser so every consumer agrees.

        Pydantic's own bool coercion raises on "" and "nonsense"; the library
        returns False. Left unaligned, an operator typo would start the CLI and
        crash the API. Both now fail closed the same way.
        """
        from property_core.config import parse_bool_flag

        return parse_bool_flag(v)

    # Polite scraping defaults (in-memory; per-process)
    rightmove_delay_seconds: float = Field(0.6, description="Delay between Rightmove requests")
    rightmove_max_concurrency: int = Field(1, description="Max concurrent Rightmove requests")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
