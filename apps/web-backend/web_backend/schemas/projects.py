"""Pydantic request/response schemas for project endpoints."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from web_backend.constants.projects import (
    MAX_BOARD_COLUMNS,
    MAX_PROJECT_NAME_LENGTH,
)


# ------------------------------------------------------------------ #
#  Validators
# ------------------------------------------------------------------ #

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _slugify(name: str) -> str:
    """Convert a project name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


# ------------------------------------------------------------------ #
#  Sub-schemas
# ------------------------------------------------------------------ #


class BoardColumnRequest(BaseModel):
    """A single board column in the creation wizard."""

    name: str = Field(..., min_length=1, max_length=50, examples=["To Do"])


class BoardColumnResponse(BaseModel):
    """Board column in API responses."""

    id: uuid.UUID
    name: str
    position: int

    model_config = {"from_attributes": True}


class MemberResponse(BaseModel):
    """Project member in API responses."""

    id: uuid.UUID
    user_id: uuid.UUID
    username: str
    first_name: str
    last_name: str
    email: str
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
#  Project creation (3-step wizard)
# ------------------------------------------------------------------ #


class ProjectCreateRequest(BaseModel):
    """POST /projects — creates project with columns and initial members.

    Maps to the 3-step wizard:
      Step 1: name + description
      Step 2: board_columns
      Step 3: member_ids (users to invite)
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PROJECT_NAME_LENGTH,
        examples=["TicketForge Core"],
    )
    description: str | None = Field(
        None,
        max_length=500,
        examples=["Main project for the TicketForge platform"],
    )
    board_columns: list[BoardColumnRequest] = Field(
        default=[],
        max_length=MAX_BOARD_COLUMNS,
        description="Custom columns. If empty, defaults are used.",
    )
    member_ids: list[uuid.UUID] = Field(
        default=[],
        description="User IDs to invite as members.",
    )

    @field_validator("name")
    @classmethod
    def check_name_not_blank(cls, v: str) -> str:
        """Ensure name is not just whitespace."""
        if not v.strip():
            msg = "Project name cannot be blank"
            raise ValueError(msg)
        return v.strip()

    @field_validator("board_columns")
    @classmethod
    def check_unique_column_names(
        cls, v: list[BoardColumnRequest]
    ) -> list[BoardColumnRequest]:
        """Ensure no duplicate column names."""
        names = [c.name.strip().lower() for c in v]
        if len(names) != len(set(names)):
            msg = "Board column names must be unique"
            raise ValueError(msg)
        return v


# ------------------------------------------------------------------ #
#  Project responses
# ------------------------------------------------------------------ #


class ProjectResponse(BaseModel):
    """Full project detail response."""

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    board_columns: list[BoardColumnResponse] = []
    members: list[MemberResponse] = []

    model_config = {"from_attributes": True}


class ProjectListItem(BaseModel):
    """Lightweight project for list views."""

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    role: str
    member_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
#  Project updates
# ------------------------------------------------------------------ #


class ProjectUpdateRequest(BaseModel):
    """PATCH /projects/:slug — update name/description."""

    name: str | None = Field(None, min_length=1, max_length=MAX_PROJECT_NAME_LENGTH)
    description: str | None = Field(None, max_length=500)

    @field_validator("name")
    @classmethod
    def check_name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            msg = "Project name cannot be blank"
            raise ValueError(msg)
        return v.strip() if v else v


# ------------------------------------------------------------------ #
#  Member management
# ------------------------------------------------------------------ #


class AddMemberRequest(BaseModel):
    """POST /projects/:slug/members — add a user to the project."""

    user_id: uuid.UUID
    role: str = Field(
        default="member",
        pattern="^(admin|member)$",
        description="Role to assign. Cannot add as owner.",
    )


class UpdateMemberRoleRequest(BaseModel):
    """PATCH /projects/:slug/members/:user_id — change a member's role."""

    role: str = Field(
        ...,
        pattern="^(admin|member)$",
        description="New role. Cannot change to/from owner via this endpoint.",
    )


# ------------------------------------------------------------------ #
#  User search (for invite typeahead)
# ------------------------------------------------------------------ #


class UserSearchResult(BaseModel):
    """Lightweight user for search-as-you-type invite."""

    id: uuid.UUID
    username: str
    first_name: str
    last_name: str
    email: str

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
#  Generic
# ------------------------------------------------------------------ #


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str
