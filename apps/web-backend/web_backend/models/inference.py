"""Inference event persistence for production prediction telemetry."""

import uuid

from sqlalchemy import Float, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from web_backend.models.base import Base, TimestampMixin


class InferenceEvent(TimestampMixin, Base):
    """Stores serving-time inference events for monitoring and traceability."""

    __tablename__ = "inference_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rail: Mapped[str] = mapped_column(String(32), nullable=False, default="direct_api")
    request_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    model_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tracking_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    predicted_bucket: Mapped[str] = mapped_column(String(16), nullable=False)
    predicted_class: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    repo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issue_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    labels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    comments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    historical_avg_completion_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    keyword_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    body_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_to_assignment_hours: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
