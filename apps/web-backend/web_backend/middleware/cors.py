"""CORS middleware configuration."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web_backend.config import get_settings


def add_cors_middleware(app: FastAPI) -> None:
    """Attach CORS middleware to the app.

    Allows credentials (cookies) so the refresh token
    HttpOnly cookie is sent cross-origin from the Next.js frontend.
    """
    settings = get_settings()
    allow_origin_regex = settings.cors_origin_regex
    if allow_origin_regex is None and os.getenv("K_SERVICE"):
        # Cloud Run web/frontend default hostname compatibility.
        allow_origin_regex = r"^https://.*\.run\.app$"

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
