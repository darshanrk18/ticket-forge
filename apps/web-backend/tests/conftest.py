"""Shared fixtures for auth tests.

Uses an async in-memory SQLite database so tests never
require a running Postgres instance.
"""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from web_backend.database import get_db
from web_backend.main import app
from web_backend.models.base import Base


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh async DB session backed by in-memory SQLite.

    Tables are created before each test and dropped after,
    giving every test a clean slate.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture()
async def client(
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """Yield an httpx AsyncClient wired to the FastAPI app.

    Overrides the ``get_db`` dependency so all routes use the
    in-memory test database instead of Postgres.
    """

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ------------------------------------------------------------------ #
#  Reusable test data
# ------------------------------------------------------------------ #

VALID_SIGNUP = {
    "username": "johndoe",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "password": "SecurePass1",
}

VALID_SIGNUP_2 = {
    "username": "janedoe",
    "first_name": "Jane",
    "last_name": "Doe",
    "email": "jane@example.com",
    "password": "SecurePass1",
}
