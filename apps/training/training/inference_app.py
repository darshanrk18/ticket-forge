"""Lightweight inference API stub for Cloud Run smoke checks.

This module intentionally returns deterministic placeholder predictions so the
serving deployment pipeline can validate HTTP readiness before model serving
integration is finalized.
"""

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="TicketForge Inference Stub", version="0.1.0")


class PredictRequest(BaseModel):
  """Input payload for the placeholder prediction endpoint."""

  text: str = Field(..., min_length=1, description="Ticket text to score.")


class PredictResponse(BaseModel):
  """Response payload for the placeholder prediction endpoint."""

  predicted_assignee: str
  confidence: float
  model_version: str


@app.get("/health")
async def health() -> dict[str, str]:
  """Return process health status."""
  return {"status": "ok"}


@app.post("/predict", response_model=PredictResponse)
async def predict(payload: PredictRequest) -> PredictResponse:
  """Return a deterministic placeholder prediction.

  Args:
      payload: Inference request containing ticket text.

  Returns:
      Placeholder prediction result used for deployment smoke testing.
  """
  _ = payload
  return PredictResponse(
    predicted_assignee="placeholder-user",
    confidence=0.5,
    model_version="stub-v1",
  )
