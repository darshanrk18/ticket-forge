"""Schemas for production inference requests and responses."""

from datetime import datetime

from pydantic import BaseModel, Field


class TicketSizePredictionRequest(BaseModel):
    """Raw ticket payload used for size prediction."""

    title: str = Field(..., min_length=1, max_length=500)
    body: str = Field(default="", max_length=5000)
    repo: str | None = Field(default=None, max_length=255)
    issue_type: str | None = Field(default=None, max_length=64)
    labels: list[str] = Field(default_factory=list)
    comments_count: int = Field(default=0, ge=0)
    historical_avg_completion_hours: float = Field(default=0.0, ge=0.0)
    created_at: datetime | None = None
    assigned_at: datetime | None = None
    rail: str = Field(default="direct_api", max_length=32)


class InferenceModelMetadataResponse(BaseModel):
    """MLflow-backed serving metadata for the current model."""

    model_name: str
    model_stage: str | None = None
    model_version: str | None = None
    model_run_id: str | None = None
    tracking_uri: str | None = None
    selector: str


class InferenceFeatureSummaryResponse(BaseModel):
    """Human-readable feature summary for debugging and drift reporting."""

    repo: str
    labels: list[str]
    keyword_count: int
    comments_count: int
    historical_avg_completion_hours: float
    title_length: int
    body_length: int
    time_to_assignment_hours: float


class TicketSizePredictionResponse(BaseModel):
    """Prediction response returned by the deployed backend."""

    predicted_bucket: str
    predicted_class: int
    confidence: float
    class_probabilities: dict[str, float]
    latency_ms: float
    model: InferenceModelMetadataResponse
    features: InferenceFeatureSummaryResponse


class InferenceMonitoringRecordResponse(BaseModel):
    """Serving-time telemetry record exported for monitoring and drift checks."""

    created_at: datetime
    repo: str | None = None
    issue_type: str | None = None
    predicted_bucket: str
    model_version: str | None = None
    rail: str
    latency_ms: float
    confidence: float
    comments_count: int
    historical_avg_completion_hours: float
    keyword_count: int
    title_length: int
    body_length: int
    time_to_assignment_hours: float
