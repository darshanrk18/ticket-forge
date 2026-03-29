"""API v1 router — aggregates all v1 sub-routers."""

from fastapi import APIRouter

from web_backend.api.v1.auth import router as auth_router
from web_backend.api.v1.projects import router as projects_router
from web_backend.api.v1.tickets import router as tickets_router
from web_backend.api.v1.users import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(projects_router)
router.include_router(tickets_router)
router.include_router(users_router)
