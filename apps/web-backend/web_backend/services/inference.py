"""Production inference service for ticket size prediction."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from time import perf_counter
from typing import Any

import mlflow
import mlflow.sklearn
import numpy as np
from ml_core.embeddings import get_embedding_service
from ml_core.keywords import get_keyword_extractor
from mlflow.tracking import MlflowClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web_backend.config import get_settings
from web_backend.models.inference import InferenceEvent
from web_backend.schemas.inference import (
    InferenceMonitoringRecordResponse,
    InferenceFeatureSummaryResponse,
    InferenceModelMetadataResponse,
    TicketSizePredictionRequest,
    TicketSizePredictionResponse,
)

logger = logging.getLogger(__name__)

_SIZE_BUCKET_LABELS: dict[int, str] = {
    0: "S",
    1: "M",
    2: "L",
    3: "XL",
}
_REPO_FEATURE_ORDER = (
    "ansible/ansible",
    "hashicorp/terraform",
    "prometheus/prometheus",
)
_CODE_BLOCK_RE = re.compile(r"```(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_MAX_TTA_HOURS = 720.0


@dataclass(frozen=True, slots=True)
class LoadedModel:
    """Loaded production model and its serving metadata."""

    estimator: Any
    selector: str
    tracking_uri: str | None
    model_name: str
    model_stage: str | None
    model_version: str | None
    model_run_id: str | None


def _tracking_uri() -> str | None:
    """Return the explicit tracking URI configured for backend serving."""
    return get_settings().mlflow_tracking_uri


def _model_cache_key() -> tuple[str | None, str | None, str]:
    """Build a stable cache key for the loaded model bundle."""
    settings = get_settings()
    return (
        settings.mlflow_tracking_uri,
        settings.serving_model_version,
        settings.mlflow_model_stage,
    )


def _truncate_code_block(code: str) -> str:
    """Truncate long fenced code blocks before embedding."""
    lines = code.strip().splitlines()
    if len(lines) <= 15:
        return "\n".join(lines)
    if len(lines) <= 50:
        return "\n".join(lines[:5] + ["..."] + lines[-5:])
    return "\n".join(lines[:10] + ["..."] + lines[-10:])


def _find_balanced_section_end(
    text: str,
    start_index: int,
    opening: str,
    closing: str,
) -> int:
    """Return the closing delimiter index for a balanced markdown section."""
    depth = 1
    index = start_index
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _strip_markdown_links(text: str) -> str:
    """Strip markdown image/link syntax without regex backtracking."""
    chunks: list[str] = []
    index = 0

    while index < len(text):
        is_image = text.startswith("![", index)
        if is_image or text[index] == "[":
            label_start = index + (2 if is_image else 1)
            label_end = _find_balanced_section_end(text, label_start, "[", "]")
            if (
                label_end != -1
                and label_end + 1 < len(text)
                and text[label_end + 1] == "("
            ):
                target_end = _find_balanced_section_end(
                    text,
                    label_end + 2,
                    "(",
                    ")",
                )
                if target_end != -1:
                    if not is_image:
                        chunks.append(text[label_start:label_end])
                    index = target_end + 1
                    continue

        chunks.append(text[index])
        index += 1

    return "".join(chunks)


def _normalize_ticket_text(title: str, body: str) -> str:
    """Normalize markdown-heavy ticket text into a model-friendly payload."""
    safe_body = body or ""

    def _replace_code_block(match: re.Match[str]) -> str:
        return _truncate_code_block(match.group(1))

    safe_body = _CODE_BLOCK_RE.sub(_replace_code_block, safe_body)
    safe_body = _strip_markdown_links(safe_body)
    safe_body = _INLINE_CODE_RE.sub(r"\1", safe_body)
    safe_body = re.sub(r"[>#*_~-]", " ", safe_body)
    safe_body = re.sub(r"\n{3,}", "\n\n", safe_body)
    safe_body = re.sub(r"\s+", " ", safe_body).strip()
    combined = f"{title.strip()}\n\n{safe_body}".strip()
    return combined[:4000]


def _coerce_datetime(value: datetime | None) -> datetime | None:
    """Normalize possibly-naive datetimes to UTC-aware values."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _time_to_assignment_hours(
    created_at: datetime | None,
    assigned_at: datetime | None,
) -> float:
    """Compute time to assignment in hours with the training-time cap."""
    created = _coerce_datetime(created_at)
    assigned = _coerce_datetime(assigned_at)
    if created is None or assigned is None:
        return 0.0
    diff_hours = max((assigned - created).total_seconds() / 3600.0, 0.0)
    return float(min(diff_hours, _MAX_TTA_HOURS))


def _extract_keywords(text: str) -> list[str]:
    """Return the top technical keywords detected in the normalized text."""
    return get_keyword_extractor().extract(text, top_n=10)


def _embed_text(text: str) -> np.ndarray:
    """Generate the 384-dim embedding used during training."""
    return get_embedding_service(model_name="all-MiniLM-L6-v2").embed_text(text)


def _build_feature_vector(
    payload: TicketSizePredictionRequest,
) -> tuple[np.ndarray, InferenceFeatureSummaryResponse]:
    """Build the exact feature vector expected by the trained classifier."""
    normalized_text = _normalize_ticket_text(payload.title, payload.body)
    keywords = _extract_keywords(normalized_text)
    embedding = _embed_text(normalized_text).astype(np.float32)

    repo = (payload.repo or "").strip()
    labels = [label.strip().lower() for label in payload.labels if label.strip()]
    repo_one_hot = [
        1.0 if repo == repo_name else 0.0 for repo_name in _REPO_FEATURE_ORDER
    ]
    title_length = len(payload.title or "")
    body_length = len(payload.body or "")
    keyword_count = len(keywords)
    time_to_assignment = _time_to_assignment_hours(
        payload.created_at, payload.assigned_at
    )

    engineered_features = np.array(
        repo_one_hot
        + [
            1.0 if "bug" in labels else 0.0,
            1.0 if "enhancement" in labels else 0.0,
            1.0 if "crash" in labels else 0.0,
            float(payload.comments_count),
            float(payload.historical_avg_completion_hours),
            float(keyword_count),
            float(title_length),
            float(body_length),
            float(time_to_assignment),
        ],
        dtype=np.float32,
    )
    feature_vector = np.nan_to_num(
        np.hstack([embedding, engineered_features]),
        nan=0.0,
    ).reshape(1, -1)
    summary = InferenceFeatureSummaryResponse(
        repo=repo,
        labels=labels,
        keyword_count=keyword_count,
        comments_count=payload.comments_count,
        historical_avg_completion_hours=float(payload.historical_avg_completion_hours),
        title_length=title_length,
        body_length=body_length,
        time_to_assignment_hours=round(time_to_assignment, 6),
    )
    return feature_vector, summary


def _load_version_metadata(client: MlflowClient) -> tuple[str, str | None, str | None]:
    """Resolve the exact model selector and metadata for serving."""
    settings = get_settings()
    if settings.serving_model_version:
        version = client.get_model_version(
            settings.mlflow_registered_model_name,
            settings.serving_model_version,
        )
        return settings.serving_model_version, None, version.run_id

    versions = client.get_latest_versions(
        settings.mlflow_registered_model_name,
        stages=[settings.mlflow_model_stage],
    )
    if not versions:
        msg = (
            f"No model version found for "
            f"{settings.mlflow_registered_model_name}:{settings.mlflow_model_stage}"
        )
        raise RuntimeError(msg)

    version = versions[0]
    return str(version.version), settings.mlflow_model_stage, version.run_id


@lru_cache(maxsize=1)
def _load_model(_cache_key: tuple[str | None, str | None, str]) -> LoadedModel:
    """Load the currently configured model from MLflow once per process."""
    settings = get_settings()
    tracking_uri = _tracking_uri()
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    client = MlflowClient(tracking_uri=tracking_uri) if tracking_uri else MlflowClient()
    resolved_version, resolved_stage, run_id = _load_version_metadata(client)
    selector = settings.serving_model_version or settings.mlflow_model_stage
    model_uri = f"models:/{settings.mlflow_registered_model_name}/{selector}"
    estimator = mlflow.sklearn.load_model(model_uri)

    logger.info(
        "Loaded serving model selector=%s version=%s tracking_uri=%s",
        selector,
        resolved_version,
        tracking_uri,
    )
    return LoadedModel(
        estimator=estimator,
        selector=selector,
        tracking_uri=tracking_uri,
        model_name=settings.mlflow_registered_model_name,
        model_stage=resolved_stage,
        model_version=resolved_version,
        model_run_id=run_id,
    )


def get_loaded_model() -> LoadedModel:
    """Return the cached serving model bundle."""
    return _load_model(_model_cache_key())


def _softmax(values: np.ndarray) -> np.ndarray:
    """Numerically stable softmax."""
    shifted = values - np.max(values)
    exp_values = np.exp(shifted)
    return exp_values / np.sum(exp_values)


def _class_probabilities(
    estimator: Any, features: np.ndarray
) -> tuple[dict[str, float], float]:
    """Return normalized class probabilities and top confidence."""
    class_ids = list(getattr(estimator, "classes_", range(len(_SIZE_BUCKET_LABELS))))
    probability_map = {label: 0.0 for label in _SIZE_BUCKET_LABELS.values()}

    if hasattr(estimator, "predict_proba"):
        probabilities = np.asarray(estimator.predict_proba(features))[0]
    elif hasattr(estimator, "decision_function"):
        decision_scores = np.asarray(estimator.decision_function(features))
        if decision_scores.ndim == 1:
            decision_scores = np.stack([-decision_scores, decision_scores], axis=1)
        probabilities = _softmax(decision_scores[0])
    else:
        predicted_class = int(np.asarray(estimator.predict(features))[0])
        probabilities = np.zeros(len(class_ids), dtype=np.float64)
        if predicted_class in class_ids:
            probabilities[class_ids.index(predicted_class)] = 1.0

    for index, class_id in enumerate(class_ids):
        bucket = _SIZE_BUCKET_LABELS.get(int(class_id), str(class_id))
        if index < len(probabilities):
            probability_map[bucket] = round(float(probabilities[index]), 6)

    confidence = max(probability_map.values(), default=0.0)
    return probability_map, round(confidence, 6)


def _request_fingerprint(
    payload: TicketSizePredictionRequest,
    summary: InferenceFeatureSummaryResponse,
) -> str:
    """Create a deterministic fingerprint for the inference request."""
    fingerprint_source = {
        "title": payload.title,
        "body": payload.body,
        "repo": payload.repo,
        "issue_type": payload.issue_type,
        "labels": summary.labels,
        "comments_count": payload.comments_count,
        "historical_avg_completion_hours": payload.historical_avg_completion_hours,
        "created_at": payload.created_at.isoformat() if payload.created_at else None,
        "assigned_at": payload.assigned_at.isoformat() if payload.assigned_at else None,
    }
    encoded = json.dumps(fingerprint_source, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def _store_inference_event(
    db: AsyncSession,
    *,
    payload: TicketSizePredictionRequest,
    summary: InferenceFeatureSummaryResponse,
    model: LoadedModel,
    predicted_bucket: str,
    predicted_class: int,
    confidence: float,
    latency_ms: float,
) -> None:
    """Persist inference telemetry without failing the main request path."""
    event = InferenceEvent(
        rail=payload.rail,
        request_fingerprint=_request_fingerprint(payload, summary),
        model_name=model.model_name,
        model_stage=model.model_stage,
        model_version=model.model_version,
        model_run_id=model.model_run_id,
        tracking_uri=model.tracking_uri,
        predicted_bucket=predicted_bucket,
        predicted_class=predicted_class,
        confidence=confidence,
        latency_ms=latency_ms,
        repo=summary.repo or None,
        issue_type=payload.issue_type,
        labels=summary.labels,
        comments_count=summary.comments_count,
        historical_avg_completion_hours=summary.historical_avg_completion_hours,
        keyword_count=summary.keyword_count,
        title_length=summary.title_length,
        body_length=summary.body_length,
        time_to_assignment_hours=summary.time_to_assignment_hours,
    )
    db.add(event)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Failed to persist inference event")


def current_model_metadata() -> InferenceModelMetadataResponse:
    """Return metadata for the currently served MLflow model."""
    model = get_loaded_model()
    return InferenceModelMetadataResponse(
        model_name=model.model_name,
        model_stage=model.model_stage,
        model_version=model.model_version,
        model_run_id=model.model_run_id,
        tracking_uri=model.tracking_uri,
        selector=model.selector,
    )


async def predict_ticket_size(
    db: AsyncSession,
    payload: TicketSizePredictionRequest,
) -> TicketSizePredictionResponse:
    """Run live ticket size prediction against the promoted production model."""
    started_at = perf_counter()
    model = get_loaded_model()
    features, summary = _build_feature_vector(payload)
    predicted_class = int(np.asarray(model.estimator.predict(features))[0])
    predicted_bucket = _SIZE_BUCKET_LABELS.get(predicted_class, str(predicted_class))
    class_probabilities, confidence = _class_probabilities(model.estimator, features)
    latency_ms = round((perf_counter() - started_at) * 1000.0, 3)

    await _store_inference_event(
        db,
        payload=payload,
        summary=summary,
        model=model,
        predicted_bucket=predicted_bucket,
        predicted_class=predicted_class,
        confidence=confidence,
        latency_ms=latency_ms,
    )

    logger.info(
        "Served ticket-size inference model=%s version=%s latency_ms=%.3f bucket=%s",
        model.model_name,
        model.model_version,
        latency_ms,
        predicted_bucket,
    )
    return TicketSizePredictionResponse(
        predicted_bucket=predicted_bucket,
        predicted_class=predicted_class,
        confidence=confidence,
        class_probabilities=class_probabilities,
        latency_ms=latency_ms,
        model=current_model_metadata(),
        features=summary,
    )


async def export_recent_inference_records(
    db: AsyncSession,
    *,
    limit: int = 1000,
) -> list[InferenceMonitoringRecordResponse]:
    """Export recent serving telemetry for monitoring workflows."""
    result = await db.execute(
        select(InferenceEvent).order_by(InferenceEvent.created_at.desc()).limit(limit)
    )
    events = result.scalars().all()
    return [
        InferenceMonitoringRecordResponse(
            created_at=event.created_at,
            repo=event.repo,
            issue_type=event.issue_type,
            predicted_bucket=event.predicted_bucket,
            model_version=event.model_version,
            rail=event.rail,
            latency_ms=event.latency_ms,
            confidence=event.confidence,
            comments_count=event.comments_count,
            historical_avg_completion_hours=event.historical_avg_completion_hours,
            keyword_count=event.keyword_count,
            title_length=event.title_length,
            body_length=event.body_length,
            time_to_assignment_hours=event.time_to_assignment_hours,
        )
        for event in events
    ]
