"""CORS middleware configuration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web_backend.config import get_settings


def add_cors_middleware(app: FastAPI) -> None:
    """Attach CORS middleware to the app.

    Allows credentials (cookies) so the refresh token
    HttpOnly cookie is sent cross-origin from the Next.js frontend.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
