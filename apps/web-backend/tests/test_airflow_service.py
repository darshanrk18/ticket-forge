"""Tests for web-backend routes and services."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from web_backend.main import app
from web_backend.services.airflow import (
    DagRunResult,
    DagRunStatus,
    _get_airflow_config,
    _map_airflow_state,
    trigger_resume_ingest_batch,
    get_dag_run_status,
)


client = TestClient(app)


class TestAirflowStateMapping:
    """Tests for Airflow state mapping logic."""

    def test_map_airflow_state_queued(self) -> None:
        """Maps queued state."""
        result = _map_airflow_state("queued")
        assert result == DagRunStatus.QUEUED

    def test_map_airflow_state_running(self) -> None:
        """Maps running state."""
        result = _map_airflow_state("running")
        assert result == DagRunStatus.RUNNING

    def test_map_airflow_state_success(self) -> None:
        """Maps success state."""
        result = _map_airflow_state("success")
        assert result == DagRunStatus.SUCCESS

    def test_map_airflow_state_failed(self) -> None:
        """Maps failed state."""
        result = _map_airflow_state("failed")
        assert result == DagRunStatus.FAILED


class TestAirflowConfig:
    """Tests for Airflow configuration detection."""

    def test_get_airflow_config_returns_none_when_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns None when AIRFLOW_BASE_URL not set."""
        monkeypatch.delenv("AIRFLOW_BASE_URL", raising=False)
        result = _get_airflow_config()
        assert result is None

    def test_get_airflow_config_extracts_url_and_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Extracts base_url, username, password from env."""
        monkeypatch.setenv("AIRFLOW_BASE_URL", "http://localhost:8080")
        monkeypatch.setenv("AIRFLOW_USERNAME", "test_user")
        monkeypatch.setenv("AIRFLOW_PASSWORD", "test_pass")

        result = _get_airflow_config()

        assert result is not None
        base_url, username, password = result
        assert base_url == "http://localhost:8080"
        assert username == "test_user"
        assert password == "test_pass"

    def test_get_airflow_config_defaults_username_password(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Uses default credentials when not set."""
        monkeypatch.setenv("AIRFLOW_BASE_URL", "http://localhost:8080")
        monkeypatch.delenv("AIRFLOW_USERNAME", raising=False)
        monkeypatch.delenv("AIRFLOW_PASSWORD", raising=False)

        result = _get_airflow_config()

        assert result is not None
        base_url, username, password = result
        assert username == "airflow"
        assert password == "airflow"


class TestDagRunResult:
    """Tests for DagRunResult data class."""

    def test_dag_run_result_post_init_sets_timestamp(self) -> None:
        """DagRunResult sets triggered_at if not provided."""
        result = DagRunResult(
            dag_id="test_dag",
            run_id="run_123",
            status=DagRunStatus.QUEUED,
        )

        assert result.triggered_at
        assert "T" in result.triggered_at  # ISO format has T

    def test_dag_run_result_preserves_conf(self) -> None:
        """DagRunResult stores conf dict."""
        conf = {"key": "value"}
        result = DagRunResult(
            dag_id="test_dag",
            run_id="run_123",
            status=DagRunStatus.SUCCESS,
            conf=conf,
        )

        assert result.conf == conf


class TestTriggerResumeIngestBatch:
    """Tests for triggering resume ingest DAG."""

    @patch("web_backend.services.airflow._get_airflow_config")
    def test_trigger_resume_ingest_batch_without_airflow(
        self, mock_config: MagicMock
    ) -> None:
        """Uses dummy DAG run when Airflow not configured."""
        mock_config.return_value = None

        items = [
            {
                "filename": "resume1.pdf",
                "content_base64": "base64data",
                "github_username": "alice",
                "full_name": "Alice Smith",
            }
        ]

        result = trigger_resume_ingest_batch(items)

        assert result.dag_id == "resume_etl"
        assert result.status == DagRunStatus.QUEUED

    @patch("web_backend.services.airflow.httpx.post")
    @patch("web_backend.services.airflow._get_airflow_config")
    def test_trigger_resume_ingest_batch_calls_airflow_api(
        self,
        mock_config: MagicMock,
        mock_post: MagicMock,
    ) -> None:
        """Calls Airflow REST API when configured."""
        mock_config.return_value = ("http://airflow:8080", "user", "pass")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "dag_id": "resume_etl",
            "dag_run_id": "run_123",
            "state": "queued",
            "conf": {},
        }
        mock_post.return_value = mock_response

        items = [
            {
                "filename": "resume.pdf",
                "content_base64": "data",
                "github_username": "bob",
            }
        ]

        result = trigger_resume_ingest_batch(items)

        assert mock_post.called
        assert isinstance(result, DagRunResult)


class TestGetDagRunStatus:
    """Tests for checking DAG run status."""

    @patch("web_backend.services.airflow._get_airflow_config")
    def test_get_dag_run_status_without_airflow_returns_none(
        self, mock_config: MagicMock
    ) -> None:
        """Returns None when Airflow not configured and run_id not in dummy store."""
        mock_config.return_value = None

        result = get_dag_run_status("unknown_run")

        assert result is None


class TestResumeUploadEndpoint:
    """Tests for /resumes/upload FastAPI route."""

    @patch("web_backend.routes.resumes.trigger_resume_ingest_batch")
    def test_upload_resumes_returns_trigger_response(
        self, mock_trigger: MagicMock
    ) -> None:
        """POST /api/v1/resumes/upload returns PipelineTriggerResponse."""
        mock_trigger.return_value = MagicMock(
            dag_id="resume_etl",
            run_id="run_123",
            status=DagRunStatus.QUEUED,
            triggered_at="2025-01-01T12:00:00Z",
        )

        payload = {
            "resumes": [
                {
                    "filename": "resume1.pdf",
                    "content_base64": "ZmlsZSBjb250ZW50",
                    "github_username": "alice",
                    "full_name": "Alice Smith",
                }
            ]
        }

        response = client.post("/api/v1/resumes/upload", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["dag_id"] == "resume_etl"
        assert data["run_id"] == "run_123"
        assert data["status"] == "queued"

    def test_upload_resumes_rejects_empty_list(self) -> None:
        """POST /api/v1/resumes/upload rejects empty resumes list."""
        payload = {"resumes": []}

        response = client.post("/api/v1/resumes/upload", json=payload)

        assert response.status_code == 400


class TestPipelineStatusEndpoint:
    """Tests for /api/v1/resumes/status/{run_id} FastAPI route."""

    @patch("web_backend.routes.resumes.get_dag_run_status")
    def test_get_pipeline_status_returns_response(self, mock_status: MagicMock) -> None:
        """GET /api/v1/resumes/status/{run_id} returns PipelineStatusResponse."""
        mock_result = DagRunResult(
            dag_id="resume_etl",
            run_id="run_123",
            status=DagRunStatus.SUCCESS,
            conf={},
            triggered_at="2025-01-01T12:00:00Z",
        )
        mock_status.return_value = mock_result

        response = client.get("/api/v1/resumes/status/run_123")

        assert response.status_code == 200
        data = response.json()
        assert data["dag_id"] == "resume_etl"
        assert data["status"] == "success"

    @patch("web_backend.routes.resumes.get_dag_run_status")
    def test_get_pipeline_status_returns_404_when_not_found(
        self, mock_status: MagicMock
    ) -> None:
        """GET /api/v1/resumes/status/{run_id} returns 404 if run not found."""
        mock_status.return_value = None

        response = client.get("/api/v1/resumes/status/unknown")

        assert response.status_code == 404
