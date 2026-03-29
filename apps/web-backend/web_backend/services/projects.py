"""Project business logic.

Handles project creation, membership, board columns, and user search.
Routes call these — no direct DB queries in routes.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from web_backend.constants.projects import (
    DEFAULT_BOARD_COLUMNS,
    MANAGEMENT_ROLES,
    ROLE_MEMBER,
    ROLE_OWNER,
)
from web_backend.models.project import (
    Project,
    ProjectBoardColumn,
    ProjectMember,
)
from web_backend.models.user import AuthUser
from web_backend.schemas.projects import (
    AddMemberRequest,
    MemberResponse,
    ProjectCreateRequest,
    ProjectListItem,
    _slugify,
)


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #


async def _unique_slug(db: AsyncSession, base_slug: str) -> str:
    """Generate a unique slug, appending a counter if needed."""
    slug = base_slug
    counter = 1
    while True:
        exists = await db.execute(select(Project.id).where(Project.slug == slug))
        if exists.scalar_one_or_none() is None:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


async def _get_membership(
    db: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ProjectMember | None:
    """Fetch a user's membership in a project."""
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def _get_project_by_slug(
    db: AsyncSession,
    slug: str,
) -> Project | None:
    """Fetch a project by slug with columns and members loaded."""
    result = await db.execute(
        select(Project)
        .where(Project.slug == slug)
        .options(
            selectinload(Project.board_columns),
            selectinload(Project.members).selectinload(ProjectMember.user),
        )
    )
    return result.scalar_one_or_none()


# ------------------------------------------------------------------ #
#  Create project
# ------------------------------------------------------------------ #


async def create_project(
    db: AsyncSession,
    data: ProjectCreateRequest,
    owner: AuthUser,
) -> Project:
    """Create a project, add owner, set up board columns, invite members.

    Returns the fully-loaded Project with members and columns.

    Raises:
        ValueError: If any invited user_id doesn't exist.
    """
    # Generate unique slug
    base_slug = _slugify(data.name)
    slug = await _unique_slug(db, base_slug)

    # Create project
    project = Project(
        name=data.name,
        slug=slug,
        description=data.description,
        created_by=owner.id,
    )
    db.add(project)
    await db.flush()  # Get project.id

    # Add owner as first member
    owner_member = ProjectMember(
        project_id=project.id,
        user_id=owner.id,
        role=ROLE_OWNER,
    )
    db.add(owner_member)

    # Board columns — use custom or defaults
    column_names = (
        [c.name.strip() for c in data.board_columns]
        if data.board_columns
        else DEFAULT_BOARD_COLUMNS
    )
    for position, col_name in enumerate(column_names):
        col = ProjectBoardColumn(
            project_id=project.id,
            name=col_name,
            position=position,
        )
        db.add(col)

    # Invite additional members
    for member_user_id in data.member_ids:
        # Skip if it's the owner themselves
        if member_user_id == owner.id:
            continue

        # Verify user exists
        user_result = await db.execute(
            select(AuthUser.id).where(
                AuthUser.id == member_user_id,
                AuthUser.is_active.is_(True),
            )
        )
        if user_result.scalar_one_or_none() is None:
            msg = f"User {member_user_id} not found"
            raise ValueError(msg)

        member = ProjectMember(
            project_id=project.id,
            user_id=member_user_id,
            role=ROLE_MEMBER,
        )
        db.add(member)

    await db.commit()

    # Reload with relationships
    loaded = await _get_project_by_slug(db, slug)
    assert loaded is not None  # noqa: S101
    return loaded


# ------------------------------------------------------------------ #
#  List user's projects
# ------------------------------------------------------------------ #


async def list_user_projects(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[ProjectListItem]:
    """Return all projects the user is a member of."""
    result = await db.execute(
        select(
            Project.id,
            Project.name,
            Project.slug,
            Project.description,
            ProjectMember.role,
            Project.created_at,
            func.count(ProjectMember.id)
            .over(partition_by=Project.id)
            .label("member_count"),
        )
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user_id)
        .order_by(Project.created_at.desc())
    )
    rows = result.all()

    return [
        ProjectListItem(
            id=row.id,
            name=row.name,
            slug=row.slug,
            description=row.description,
            role=row.role,
            member_count=row.member_count,
            created_at=row.created_at,
        )
        for row in rows
    ]


# ------------------------------------------------------------------ #
#  Get project detail
# ------------------------------------------------------------------ #


async def get_project_detail(
    db: AsyncSession,
    slug: str,
    user_id: uuid.UUID,
) -> tuple[Project, ProjectMember]:
    """Fetch project detail. Verifies user is a member.

    Returns:
        Tuple of (project, membership).

    Raises:
        ValueError: If project not found or user not a member.
    """
    project = await _get_project_by_slug(db, slug)
    if project is None:
        msg = "Project not found"
        raise ValueError(msg)

    membership = await _get_membership(db, project.id, user_id)
    if membership is None:
        msg = "You are not a member of this project"
        raise ValueError(msg)

    return project, membership


# ------------------------------------------------------------------ #
#  Update project
# ------------------------------------------------------------------ #


async def update_project(
    db: AsyncSession,
    slug: str,
    user_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
) -> Project:
    """Update project name/description. Requires owner or admin.

    Raises:
        ValueError: If not found, not a member, or insufficient role.
    """
    project, membership = await get_project_detail(db, slug, user_id)

    if membership.role not in MANAGEMENT_ROLES:
        msg = "Only owners and admins can update project settings"
        raise PermissionError(msg)

    if name is not None:
        project.name = name
        project.slug = await _unique_slug(db, _slugify(name))
    if description is not None:
        project.description = description

    await db.commit()
    await db.refresh(project)
    return project


# ------------------------------------------------------------------ #
#  Delete project
# ------------------------------------------------------------------ #


async def delete_project(
    db: AsyncSession,
    slug: str,
    user_id: uuid.UUID,
) -> None:
    """Delete a project. Only owner can delete.

    Raises:
        ValueError: If not found or not a member.
        PermissionError: If not the owner.
    """
    project, membership = await get_project_detail(db, slug, user_id)

    if membership.role != ROLE_OWNER:
        msg = "Only the project owner can delete a project"
        raise PermissionError(msg)

    await db.delete(project)
    await db.commit()


# ------------------------------------------------------------------ #
#  Member management
# ------------------------------------------------------------------ #


async def add_member(
    db: AsyncSession,
    slug: str,
    requester_id: uuid.UUID,
    data: AddMemberRequest,
) -> MemberResponse:
    """Add a member to a project. Requires owner or admin.

    Raises:
        ValueError: If user not found or already a member.
        PermissionError: If requester lacks permission.
    """
    project, requester_membership = await get_project_detail(db, slug, requester_id)

    if requester_membership.role not in MANAGEMENT_ROLES:
        msg = "Only owners and admins can add members"
        raise PermissionError(msg)

    # Verify target user exists
    user_result = await db.execute(
        select(AuthUser).where(
            AuthUser.id == data.user_id,
            AuthUser.is_active.is_(True),
        )
    )
    target_user = user_result.scalar_one_or_none()
    if target_user is None:
        msg = "User not found"
        raise ValueError(msg)

    # Check not already a member
    existing = await _get_membership(db, project.id, data.user_id)
    if existing is not None:
        msg = "User is already a member of this project"
        raise ValueError(msg)

    member = ProjectMember(
        project_id=project.id,
        user_id=data.user_id,
        role=data.role,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)

    return MemberResponse(
        id=member.id,
        user_id=target_user.id,
        username=target_user.username,
        first_name=target_user.first_name,
        last_name=target_user.last_name,
        email=target_user.email,
        role=member.role,
        joined_at=member.joined_at,
    )


async def remove_member(
    db: AsyncSession,
    slug: str,
    requester_id: uuid.UUID,
    target_user_id: uuid.UUID,
) -> None:
    """Remove a member from a project.

    Rules:
      - Owner can remove anyone except themselves.
      - Admin can remove members (not other admins or owners).
      - Members can remove themselves (leave).

    Raises:
        ValueError: If project/member not found.
        PermissionError: If action not allowed.
    """
    project, requester_membership = await get_project_detail(db, slug, requester_id)

    # Self-removal (leaving) — anyone except owner can leave
    if requester_id == target_user_id:
        if requester_membership.role == ROLE_OWNER:
            msg = "Owner cannot leave. Transfer ownership or delete the project."
            raise PermissionError(msg)
        await db.delete(requester_membership)
        await db.commit()
        return

    # Removing someone else — requires management role
    if requester_membership.role not in MANAGEMENT_ROLES:
        msg = "Only owners and admins can remove members"
        raise PermissionError(msg)

    target_membership = await _get_membership(db, project.id, target_user_id)
    if target_membership is None:
        msg = "User is not a member of this project"
        raise ValueError(msg)

    # Admins can't remove owners or other admins
    if (
        requester_membership.role != ROLE_OWNER
        and target_membership.role in MANAGEMENT_ROLES
    ):
        msg = "Only the owner can remove admins"
        raise PermissionError(msg)

    # Can't remove the owner
    if target_membership.role == ROLE_OWNER:
        msg = "Cannot remove the project owner"
        raise PermissionError(msg)

    await db.delete(target_membership)
    await db.commit()


async def update_member_role(
    db: AsyncSession,
    slug: str,
    requester_id: uuid.UUID,
    target_user_id: uuid.UUID,
    new_role: str,
) -> MemberResponse:
    """Change a member's role. Only owner can do this.

    Raises:
        ValueError: If project/member not found.
        PermissionError: If requester is not the owner.
    """
    project, requester_membership = await get_project_detail(db, slug, requester_id)

    if requester_membership.role != ROLE_OWNER:
        msg = "Only the project owner can change roles"
        raise PermissionError(msg)

    if requester_id == target_user_id:
        msg = "Owner cannot change their own role"
        raise PermissionError(msg)

    target_membership = await _get_membership(db, project.id, target_user_id)
    if target_membership is None:
        msg = "User is not a member of this project"
        raise ValueError(msg)

    target_membership.role = new_role
    await db.commit()
    await db.refresh(target_membership)

    # Fetch user info for response
    user_result = await db.execute(
        select(AuthUser).where(AuthUser.id == target_user_id)
    )
    user = user_result.scalar_one()

    return MemberResponse(
        id=target_membership.id,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        role=target_membership.role,
        joined_at=target_membership.joined_at,
    )


# ------------------------------------------------------------------ #
#  User search (for invite typeahead)
# ------------------------------------------------------------------ #


async def search_users(
    db: AsyncSession,
    query: str,
    project_slug: str | None = None,
    limit: int = 10,
) -> list[AuthUser]:
    """Search users by email prefix. Optionally exclude existing project members.

    Args:
        query: Email prefix to search for (min 2 chars).
        project_slug: If provided, excludes users already in this project.
        limit: Max results to return.

    Returns:
        List of matching AuthUser objects.
    """
    if len(query) < 2:  # noqa: PLR2004
        return []

    stmt = (
        select(AuthUser)
        .where(
            AuthUser.is_active.is_(True),
            AuthUser.email.ilike(f"{query}%"),
        )
        .limit(limit)
    )

    # Exclude existing project members
    if project_slug is not None:
        project_result = await db.execute(
            select(Project.id).where(Project.slug == project_slug)
        )
        project_id = project_result.scalar_one_or_none()
        if project_id is not None:
            existing_ids = select(ProjectMember.user_id).where(
                ProjectMember.project_id == project_id
            )
            stmt = stmt.where(AuthUser.id.notin_(existing_ids))

    result = await db.execute(stmt)
    return list(result.scalars().all())
