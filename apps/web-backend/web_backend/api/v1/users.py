"""User endpoints (non-auth).

Currently provides the search-as-you-type endpoint used by
the project invite flow.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from web_backend.database import get_db
from web_backend.models.user import AuthUser
from web_backend.schemas.projects import UserSearchResult
from web_backend.security.dependencies import get_current_user
from web_backend.services.projects import search_users

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/search", response_model=list[UserSearchResult])
async def search_users_endpoint(
    q: str = Query(..., min_length=2, description="Email prefix to search"),
    project_slug: str | None = Query(
        None, description="Exclude members of this project"
    ),
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserSearchResult]:
    """Search registered users by email (for invite typeahead).

    Requires authentication. Optionally pass ``project_slug`` to
    exclude users who are already members of that project.
    """
    users = await search_users(db, q, project_slug=project_slug)
    return [UserSearchResult.model_validate(u) for u in users]
