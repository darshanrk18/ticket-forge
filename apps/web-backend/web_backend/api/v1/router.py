"""API v1 router — aggregates all v1 sub-routers."""

from fastapi import APIRouter

from web_backend.api.v1.auth import router as auth_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
