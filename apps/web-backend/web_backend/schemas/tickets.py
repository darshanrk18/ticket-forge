"""Pydantic request/response schemas for ticket endpoints."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ #
#  Ticket creation
# ------------------------------------------------------------------ #


class TicketCreateRequest(BaseModel):
    """POST /projects/:slug/tickets — create a ticket."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(None, max_length=5000)
    column_id: uuid.UUID
    priority: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    type: str = Field(default="task", pattern="^(task|story|bug)$")
    labels: list[str] = Field(default=[])
    due_date: date | None = None
    assignee_id: uuid.UUID | None = None


# ------------------------------------------------------------------ #
#  Ticket update
# ------------------------------------------------------------------ #


class TicketUpdateRequest(BaseModel):
    """PATCH /projects/:slug/tickets/:ticket_key — update a ticket."""

    title: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = Field(None, max_length=5000)
    priority: str | None = Field(None, pattern="^(low|medium|high|critical)$")
    type: str | None = Field(None, pattern="^(task|story|bug)$")
    labels: list[str] | None = None
    due_date: date | None = None
    assignee_id: uuid.UUID | None = None


# ------------------------------------------------------------------ #
#  Ticket move (drag-and-drop)
# ------------------------------------------------------------------ #


class TicketMoveRequest(BaseModel):
    """PATCH /projects/:slug/tickets/:ticket_key/move — move a ticket."""

    column_id: uuid.UUID
    position: int = Field(..., ge=0)


# ------------------------------------------------------------------ #
#  Responses
# ------------------------------------------------------------------ #


class TicketAssigneeResponse(BaseModel):
    """Nested assignee in ticket response."""

    id: uuid.UUID
    username: str
    first_name: str
    last_name: str
    email: str

    model_config = {"from_attributes": True}


class TicketResponse(BaseModel):
    """Full ticket response."""

    id: uuid.UUID
    project_id: uuid.UUID
    column_id: uuid.UUID
    ticket_key: str
    title: str
    description: str | None
    priority: str
    type: str
    labels: list[str]
    due_date: date | None
    position: int
    assignee: TicketAssigneeResponse | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BoardTicketsResponse(BaseModel):
    """All tickets for a project, grouped for the board."""

    tickets: list[TicketResponse]