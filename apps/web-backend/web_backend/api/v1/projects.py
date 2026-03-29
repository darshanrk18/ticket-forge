"""Project endpoints.

Thin layer — parse request, call service, return response.
No business logic lives here.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from web_backend.database import get_db
from web_backend.models.user import AuthUser
from web_backend.schemas.projects import (
    AddMemberRequest,
    MemberResponse,
    MessageResponse,
    ProjectCreateRequest,
    ProjectListItem,
    ProjectResponse,
    ProjectUpdateRequest,
    UpdateMemberRoleRequest,
    BoardColumnResponse,
)
from web_backend.security.dependencies import get_current_user
from web_backend.services.projects import (
    add_member,
    create_project,
    delete_project,
    get_project_detail,
    list_user_projects,
    remove_member,
    update_member_role,
    update_project,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


# ------------------------------------------------------------------ #
#  Helper: build ProjectResponse from ORM Project
# ------------------------------------------------------------------ #


def _project_to_response(project, members=None) -> ProjectResponse:
    """Convert ORM Project to API response with nested members/columns."""
    member_responses = []
    for m in members or project.members:
        member_responses.append(
            MemberResponse(
                id=m.id,
                user_id=m.user.id,
                username=m.user.username,
                first_name=m.user.first_name,
                last_name=m.user.last_name,
                email=m.user.email,
                role=m.role,
                joined_at=m.joined_at,
            )
        )

    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        board_columns=[
            BoardColumnResponse.model_validate(c) for c in project.board_columns
        ],
        members=member_responses,
    )


# ------------------------------------------------------------------ #
#  POST /projects — create project
# ------------------------------------------------------------------ #


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_endpoint(
    data: ProjectCreateRequest,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Create a new project (3-step wizard)."""
    try:
        project = await create_project(db, data, current_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return _project_to_response(project)


# ------------------------------------------------------------------ #
#  GET /projects — list user's projects
# ------------------------------------------------------------------ #


@router.get("", response_model=list[ProjectListItem])
async def list_projects(
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectListItem]:
    """List all projects the current user belongs to."""
    return await list_user_projects(db, current_user.id)


# ------------------------------------------------------------------ #
#  GET /projects/:slug — project detail
# ------------------------------------------------------------------ #


@router.get("/{slug}", response_model=ProjectResponse)
async def get_project(
    slug: str,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Get project detail (requires membership)."""
    try:
        project, _ = await get_project_detail(db, slug, current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return _project_to_response(project)


# ------------------------------------------------------------------ #
#  PATCH /projects/:slug — update project
# ------------------------------------------------------------------ #


@router.patch("/{slug}", response_model=ProjectResponse)
async def update_project_endpoint(
    slug: str,
    data: ProjectUpdateRequest,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Update project name/description (owner or admin)."""
    try:
        project = await update_project(
            db, slug, current_user.id, name=data.name, description=data.description
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    # Reload with relationships
    project_loaded, _ = await get_project_detail(db, project.slug, current_user.id)
    return _project_to_response(project_loaded)


# ------------------------------------------------------------------ #
#  DELETE /projects/:slug — delete project
# ------------------------------------------------------------------ #


@router.delete("/{slug}", response_model=MessageResponse)
async def delete_project_endpoint(
    slug: str,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete a project (owner only)."""
    try:
        await delete_project(db, slug, current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return MessageResponse(message="Project deleted")


# ------------------------------------------------------------------ #
#  POST /projects/:slug/members — add member
# ------------------------------------------------------------------ #


@router.post(
    "/{slug}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member_endpoint(
    slug: str,
    data: AddMemberRequest,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberResponse:
    """Add a registered user to the project (owner or admin)."""
    try:
        return await add_member(db, slug, current_user.id, data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


# ------------------------------------------------------------------ #
#  DELETE /projects/:slug/members/:user_id — remove member
# ------------------------------------------------------------------ #


@router.delete("/{slug}/members/{user_id}", response_model=MessageResponse)
async def remove_member_endpoint(
    slug: str,
    user_id: uuid.UUID,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Remove a member or leave the project."""
    try:
        await remove_member(db, slug, current_user.id, user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return MessageResponse(message="Member removed")


# ------------------------------------------------------------------ #
#  PATCH /projects/:slug/members/:user_id — update role
# ------------------------------------------------------------------ #


@router.patch("/{slug}/members/{user_id}", response_model=MemberResponse)
async def update_role_endpoint(
    slug: str,
    user_id: uuid.UUID,
    data: UpdateMemberRoleRequest,
    current_user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberResponse:
    """Change a member's role (owner only)."""
    try:
        return await update_member_role(db, slug, current_user.id, user_id, data.role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
