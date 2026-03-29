"""Project-related ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from web_backend.models.base import Base, TimestampMixin


class Project(TimestampMixin, Base):
    """Top-level project/board container."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("auth_users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Relationships
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    board_columns: Mapped[list["ProjectBoardColumn"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectBoardColumn.position",
    )
    creator: Mapped["AuthUser"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[created_by],
    )


class ProjectMember(Base):
    """Maps users to projects with a role."""

    __tablename__ = "project_members"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("auth_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        Enum("owner", "admin", "member", name="project_role", create_type=False),
        nullable=False,
        default="member",
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "user_id", name="uq_project_members_project_user"
        ),
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="members")
    user: Mapped["AuthUser"] = relationship()  # type: ignore[name-defined]  # noqa: F821


class ProjectBoardColumn(Base):
    """Configurable kanban column for a project board."""

    __tablename__ = "project_board_columns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "position", name="uq_board_columns_project_position"
        ),
        UniqueConstraint("project_id", "name", name="uq_board_columns_project_name"),
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="board_columns")
