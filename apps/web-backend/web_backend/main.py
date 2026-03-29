"""FastAPI application entry point.

Mounts versioned API routers, attaches middleware, and manages
the database lifecycle via the lifespan context manager.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from web_backend.api.v1.router import router as v1_router
from web_backend.database import close_db, init_db
from web_backend.middleware.cors import add_cors_middleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: create tables. Shutdown: close DB pool."""
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="TicketForge",
    description="AI-powered ticket assignment system",
    version="0.2.0",
    lifespan=lifespan,
)

# Middleware
add_cors_middleware(app)

# Versioned API routes (auth, etc.)
app.include_router(v1_router)

# Legacy routes (resume upload → Airflow)
# Imported conditionally — depends on services/airflow.py
# which was lost during restructure. Restore from git later.
try:
    from web_backend.routes.resumes import router as coldstart_router

    app.include_router(coldstart_router, prefix="/api/v1")
except ImportError:
    pass


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}
