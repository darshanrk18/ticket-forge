"""Async SQLAlchemy engine and session factory.

Provides ``get_db`` dependency for FastAPI route injection.
Engine is created once at startup via ``init_db`` / torn down via ``close_db``.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from web_backend.config import get_settings


def _normalize_async_database_url(database_url: str) -> str:
    """Normalize a database URL for SQLAlchemy asyncio engine usage.

    PostgreSQL URLs are coerced to the asyncpg driver so
    ``create_async_engine`` can initialize successfully even when a sync-style
    DSN (for example ``postgresql://...``) is provided via environment.

    Args:
        database_url: Raw database URL from configuration.

    Returns:
        A URL string compatible with SQLAlchemy asyncio engine expectations.
    """
    normalized_url = database_url
    if database_url.startswith("postgres://"):
        normalized_url = database_url.replace("postgres://", "postgresql://", 1)

    parsed_url = make_url(normalized_url)
    if parsed_url.get_backend_name() == "postgresql":
        parsed_url = parsed_url.set(drivername="postgresql+asyncpg")
        return str(parsed_url)

    return normalized_url


engine = create_async_engine(
    _normalize_async_database_url(get_settings().database_url),
    echo=get_settings().debug,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session and ensure it closes after use."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables. Called once at app startup."""
    from web_backend.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose the engine connection pool."""
    await engine.dispose()
