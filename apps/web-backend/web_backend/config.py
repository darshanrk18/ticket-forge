"""Application configuration via environment variables.

Uses pydantic-settings to load and validate all env vars in one place.
Access the singleton via ``get_settings()``.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = (
        "postgresql+asyncpg://ticketforge:root@localhost:5433/ticketforge"
    )

    # JWT
    jwt_secret_key: str = "change-me-in-production"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # App
    debug: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
