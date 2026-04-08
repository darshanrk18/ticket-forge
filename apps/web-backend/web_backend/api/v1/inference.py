"""Inference endpoints for production ticket size prediction."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from web_backend.database import get_db
from web_backend.schemas.inference import (
    InferenceMonitoringRecordResponse,
    InferenceModelMetadataResponse,
    TicketSizePredictionRequest,
    TicketSizePredictionResponse,
)
from web_backend.services.inference import (
    current_model_metadata,
    export_recent_inference_records,
    predict_ticket_size,
)

router = APIRouter(prefix="/inference", tags=["Inference"])


@router.get("/model", response_model=InferenceModelMetadataResponse)
async def get_model_metadata() -> InferenceModelMetadataResponse:
    """Return metadata for the production model currently loaded by the backend."""
    try:
        return current_model_metadata()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Model metadata unavailable: {exc}",
        ) from exc


@router.post("/ticket-size", response_model=TicketSizePredictionResponse)
async def predict_ticket_size_endpoint(
    payload: TicketSizePredictionRequest,
    db: AsyncSession = Depends(get_db),
) -> TicketSizePredictionResponse:
    """Predict a ticket size bucket using the currently deployed production model."""
    try:
        return await predict_ticket_size(db, payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Inference unavailable: {exc}",
        ) from exc


@router.get(
    "/monitoring/export",
    response_model=list[InferenceMonitoringRecordResponse],
)
async def export_inference_monitoring_records(
    limit: int = Query(default=1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
) -> list[InferenceMonitoringRecordResponse]:
    """Export recent inference telemetry for monitoring and drift detection."""
    try:
        return await export_recent_inference_records(db, limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Monitoring export unavailable: {exc}",
        ) from exc
