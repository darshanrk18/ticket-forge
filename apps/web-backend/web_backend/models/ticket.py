"""Project ticket ORM models."""

# Pylint doesn't fully understand SQLAlchemy's `Mapped[...]` generic.
# pylint: disable=unsubscriptable-object

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from web_backend.models.base import Base, TimestampMixin


class ProjectTicketCounter(Base):
    """Auto-increment counter for ticket keys per project."""

    __tablename__ = "project_ticket_counters"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProjectTicket(TimestampMixin, Base):
    """Ticket on a project board."""

    __tablename__ = "project_tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    column_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("project_board_columns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("auth_users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    ticket_key: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(
        Enum("low", "medium", "high", "critical", name="ticket_priority", create_type=False),
        nullable=False,
        default="medium",
    )
    type: Mapped[str] = mapped_column(
        Enum("task", "story", "bug", name="ticket_type", create_type=False),
        nullable=False,
        default="task",
    )
    labels: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("project_id", "ticket_key", name="uq_project_tickets_key"),
    )

    # Relationships
    project: Mapped["Project"] = relationship()  # type: ignore[name-defined]  # noqa: F821
    column: Mapped["ProjectBoardColumn"] = relationship()  # type: ignore[name-defined]  # noqa: F821
    assignee: Mapped["AuthUser | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[assignee_id],
    )
    creator: Mapped["AuthUser"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[created_by],
    )