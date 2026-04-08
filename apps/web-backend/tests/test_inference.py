"""Tests for production ticket-size inference endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from sqlalchemy import select

from web_backend.models.inference import InferenceEvent
from web_backend.services.inference import _build_feature_vector, _normalize_ticket_text


class _FakeEstimator:
    classes_ = np.array([0, 1, 2, 3])

    def predict(self, features: np.ndarray) -> np.ndarray:
        assert features.shape == (1, 396)
        return np.array([2])

    def predict_proba(self, _features: np.ndarray) -> np.ndarray:
        return np.array([[0.05, 0.15, 0.70, 0.10]])


def test_build_feature_vector_matches_training_shape() -> None:
    """Inference preprocessing should match the training feature layout."""
    payload = {
        "title": "Terraform crash on apply",
        "body": '```hcl\nresource "x" {}\n```\nNeed urgent fix',
        "repo": "hashicorp/terraform",
        "labels": ["bug", "crash"],
        "comments_count": 3,
        "historical_avg_completion_hours": 12.5,
        "created_at": datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        "assigned_at": datetime(2026, 4, 8, 15, 0, tzinfo=UTC),
    }

    with (
        patch(
            "web_backend.services.inference._extract_keywords",
            return_value=["terraform", "crash"],
        ),
        patch(
            "web_backend.services.inference._embed_text",
            return_value=np.ones(384, dtype=np.float32),
        ),
    ):
        features, summary = _build_feature_vector(payload=SimpleNamespace(**payload))

    assert features.shape == (1, 396)
    assert summary.repo == "hashicorp/terraform"
    assert summary.keyword_count == 2
    assert summary.time_to_assignment_hours == 3.0


def test_normalize_ticket_text_strips_markdown_links_without_dropping_labels() -> None:
    """Markdown cleanup should remove URLs/images while keeping useful link labels."""
    normalized = _normalize_ticket_text(
        "Deploy regression",
        (
            "See [deployment guide](https://example.com/docs) before rollout.\n"
            "![architecture](https://example.com/diagram.png)\n"
            "`kubectl rollout status deploy/web`"
        ),
    )

    assert "https://example.com" not in normalized
    assert "deployment guide" in normalized
    assert "architecture" not in normalized
    assert "kubectl rollout status deploy/web" in normalized


@pytest.mark.asyncio
async def test_ticket_size_prediction_endpoint_persists_event(
    client,
    db_session,
) -> None:
    """Prediction requests should return model metadata and persist telemetry."""
    fake_model = SimpleNamespace(
        estimator=_FakeEstimator(),
        selector="Production",
        tracking_uri="https://mlflow.example.run.app",
        model_name="ticket-forge-best",
        model_stage="Production",
        model_version="7",
        model_run_id="run-123",
    )

    with (
        patch(
            "web_backend.services.inference.get_loaded_model",
            return_value=fake_model,
        ),
        patch(
            "web_backend.services.inference._extract_keywords",
            return_value=["backend", "terraform", "bug"],
        ),
        patch(
            "web_backend.services.inference._embed_text",
            return_value=np.ones(384, dtype=np.float32),
        ),
    ):
        response = await client.post(
            "/api/v1/inference/ticket-size",
            json={
                "title": "Terraform apply fails in production",
                "body": "Our backend deploy crashes with a panic",
                "repo": "hashicorp/terraform",
                "issue_type": "bug",
                "labels": ["bug", "backend"],
                "comments_count": 4,
                "historical_avg_completion_hours": 18.0,
                "rail": "board_ui",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_bucket"] == "L"
    assert payload["predicted_class"] == 2
    assert payload["confidence"] == 0.7
    assert payload["class_probabilities"]["L"] == 0.7
    assert payload["model"]["model_version"] == "7"
    assert payload["model"]["selector"] == "Production"
    assert payload["features"]["keyword_count"] == 3

    result = await db_session.execute(select(InferenceEvent))
    event = result.scalar_one()
    assert event.rail == "board_ui"
    assert event.model_version == "7"
    assert event.predicted_bucket == "L"
    assert event.keyword_count == 3


@pytest.mark.asyncio
async def test_model_metadata_endpoint_returns_loaded_model(client) -> None:
    """Model metadata endpoint should expose the exact serving selector."""
    fake_model = SimpleNamespace(
        estimator=_FakeEstimator(),
        selector="7",
        tracking_uri="https://mlflow.example.run.app",
        model_name="ticket-forge-best",
        model_stage=None,
        model_version="7",
        model_run_id="run-123",
    )

    with patch(
        "web_backend.services.inference.get_loaded_model",
        return_value=fake_model,
    ):
        response = await client.get("/api/v1/inference/model")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "model_name": "ticket-forge-best",
        "model_stage": None,
        "model_version": "7",
        "model_run_id": "run-123",
        "tracking_uri": "https://mlflow.example.run.app",
        "selector": "7",
    }


@pytest.mark.asyncio
async def test_monitoring_export_endpoint_returns_recent_events(
    client,
    db_session,
) -> None:
    """Monitoring export should expose persisted inference telemetry."""
    db_session.add(
        InferenceEvent(
            rail="deploy_smoketest",
            request_fingerprint="abc123",
            model_name="ticket-forge-best",
            model_stage="Production",
            model_version="11",
            model_run_id="run-11",
            tracking_uri="https://mlflow.example.run.app",
            predicted_bucket="M",
            predicted_class=1,
            confidence=0.82,
            latency_ms=54.1,
            repo="ansible/ansible",
            issue_type="bug",
            labels=["bug", "backend"],
            comments_count=2,
            historical_avg_completion_hours=9.5,
            keyword_count=4,
            title_length=32,
            body_length=128,
            time_to_assignment_hours=1.5,
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/inference/monitoring/export?limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["predicted_bucket"] == "M"
    assert payload[0]["model_version"] == "11"
    assert payload[0]["latency_ms"] == 54.1
