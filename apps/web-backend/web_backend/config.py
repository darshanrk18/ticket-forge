"""Application configuration via environment variables.

Uses pydantic-settings to load and validate all env vars in one place.
Access the singleton via ``get_settings()``.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str | None = None
    database_host: str = "localhost"
    database_port: int = 5433
    database_name: str = "ticketforge"
    database_user: str = "ticketforge"
    database_password: str = "root"

    # JWT
    jwt_secret_key: str = "change-me-in-production"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]
    cors_origin_regex: str | None = None
    refresh_cookie_secure: bool = False
    refresh_cookie_samesite: str = "lax"
    refresh_cookie_domain: str | None = None

    # MLflow-backed serving
    mlflow_tracking_uri: str | None = None
    mlflow_registered_model_name: str = "ticket-forge-best"
    mlflow_model_stage: str = "Production"
    serving_model_version: str | None = None

    # App
    debug: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Allow CORS origins to be configured as CSV or JSON."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return stripped
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @field_validator("refresh_cookie_samesite")
    @classmethod
    def _normalize_cookie_samesite(cls, value: str) -> str:
        """Validate the cookie SameSite policy."""
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            msg = "refresh_cookie_samesite must be one of: lax, strict, none"
            raise ValueError(msg)
        return normalized

    @property
    def resolved_database_url(self) -> str:
        """Return the configured database URL or build one from components."""
        if self.database_url:
            return self.database_url
        return (
            "postgresql://"
            f"{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
