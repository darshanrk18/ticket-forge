"""Unit tests for database URL normalization."""

from web_backend.database import _normalize_async_database_url


def test_normalize_async_database_url_converts_plain_postgres() -> None:
    """Converts plain PostgreSQL URLs to asyncpg driver URLs."""
    value = _normalize_async_database_url("postgresql://u:p@localhost:5432/testdb")

    assert value.startswith("postgresql+asyncpg://")
    assert "@localhost:5432/testdb" in value


def test_normalize_async_database_url_converts_psycopg2_postgres() -> None:
    """Converts psycopg2 PostgreSQL URLs to asyncpg driver URLs."""
    value = _normalize_async_database_url(
        "postgresql+psycopg2://u:p@localhost:5432/testdb"
    )

    assert value.startswith("postgresql+asyncpg://")


def test_normalize_async_database_url_keeps_non_postgres_async_urls() -> None:
    """Keeps existing async non-Postgres URLs unchanged."""
    value = _normalize_async_database_url("sqlite+aiosqlite:///:memory:")

    assert value == "sqlite+aiosqlite:///:memory:"


def test_normalize_async_database_url_handles_postgres_alias_scheme() -> None:
    """Normalizes postgres:// alias scheme to asyncpg PostgreSQL URL."""
    value = _normalize_async_database_url("postgres://u:p@localhost:5432/testdb")

    assert value.startswith("postgresql+asyncpg://")
