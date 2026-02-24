"""Tests for the cold-start resume upload API router.

All Airflow interactions are mocked so these tests run without a live
Airflow instance.  The dummy in-memory backend is also exercised for
the happy-path flows.
"""

from __future__ import annotations

import base64
from unittest.mock import patch

from fastapi.testclient import TestClient
from web_backend.main import app
from web_backend.services.airflow import DagRunResult, DagRunStatus

client = TestClient(app)


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #

UPLOAD_URL = "/api/v1/resumes/upload"
STATUS_URL = "/api/v1/resumes/status"

_SAMPLE_B64 = base64.b64encode(b"plain text resume content").decode()


def _resume_payload(
    count: int = 1,
    username: str = "alice",
) -> dict:
    """Build a valid batch-upload request body."""
    return {
        "resumes": [
            {
                "filename": f"resume_{i}.txt",
                "content_base64": _SAMPLE_B64,
                "github_username": f"{username}_{i}" if count > 1 else username,
                "full_name": f"User {i}",
            }
            for i in range(count)
        ]
    }


# ------------------------------------------------------------------ #
#  POST /resumes/upload
# ------------------------------------------------------------------ #


class TestUploadResumes:
    """Tests for the batch resume upload endpoint."""

    def test_success_returns_trigger_response(self) -> None:
        """Happy path: trigger succeeds and returns dag_id + run_id."""
        fake = DagRunResult(
            dag_id="resume_etl",
            run_id="run_abc123",
            status=DagRunStatus.QUEUED,
            conf={},
        )
        with patch(
            "web_backend.routes.resumes.trigger_resume_ingest_batch",
            return_value=fake,
        ):
            resp = client.post(UPLOAD_URL, json=_resume_payload())

        assert resp.status_code == 200
        body = resp.json()
        assert body["dag_id"] == "resume_etl"
        assert body["run_id"] == "run_abc123"
        assert body["status"] == "queued"

    def test_multiple_resumes_accepted(self) -> None:
        """Batch with several resumes triggers one DAG run."""
        fake = DagRunResult(
            dag_id="resume_etl",
            run_id="run_batch",
            status=DagRunStatus.QUEUED,
        )
        with patch(
            "web_backend.routes.resumes.trigger_resume_ingest_batch",
            return_value=fake,
        ) as mock_trigger:
            resp = client.post(UPLOAD_URL, json=_resume_payload(count=3))

        assert resp.status_code == 200
        # The items list passed to the trigger should contain 3 entries
        items = mock_trigger.call_args[0][0]
        assert len(items) == 3

    def test_empty_resumes_returns_400(self) -> None:
        resp = client.post(UPLOAD_URL, json={"resumes": []})
        assert resp.status_code == 400
        assert "No resumes" in resp.json()["detail"]

    def test_missing_body_returns_422(self) -> None:
        resp = client.post(UPLOAD_URL, json={})
        assert resp.status_code == 422

    def test_missing_required_fields_returns_422(self) -> None:
        """Each resume item requires filename, content_base64, github_username."""
        resp = client.post(
            UPLOAD_URL,
            json={"resumes": [{"filename": "x.pdf"}]},
        )
        assert resp.status_code == 422

    def test_airflow_error_returns_502(self) -> None:
        with patch(
            "web_backend.routes.resumes.trigger_resume_ingest_batch",
            side_effect=RuntimeError("Airflow unreachable"),
        ):
            resp = client.post(UPLOAD_URL, json=_resume_payload())

        assert resp.status_code == 502
        assert "Airflow unreachable" in resp.json()["detail"]

    def test_full_name_is_optional(self) -> None:
        """full_name can be omitted from individual resume items."""
        payload = {
            "resumes": [
                {
                    "filename": "resume.txt",
                    "content_base64": _SAMPLE_B64,
                    "github_username": "alice",
                }
            ]
        }
        fake = DagRunResult(
            dag_id="resume_etl",
            run_id="run_noname",
            status=DagRunStatus.QUEUED,
        )
        with patch(
            "web_backend.routes.resumes.trigger_resume_ingest_batch",
            return_value=fake,
        ):
            resp = client.post(UPLOAD_URL, json=payload)

        assert resp.status_code == 200


# ------------------------------------------------------------------ #
#  GET /resumes/status/{run_id}
# ------------------------------------------------------------------ #


class TestGetPipelineStatus:
    """Tests for the pipeline status polling endpoint."""

    def test_known_run_returns_status(self) -> None:
        fake = DagRunResult(
            dag_id="resume_etl",
            run_id="run_abc",
            status=DagRunStatus.RUNNING,
            conf={"resumes": []},
        )
        with patch(
            "web_backend.routes.resumes.get_dag_run_status",
            return_value=fake,
        ):
            resp = client.get(f"{STATUS_URL}/run_abc")

        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == "run_abc"
        assert body["status"] == "running"
        assert body["conf"] == {"resumes": []}

    def test_unknown_run_returns_404(self) -> None:
        with patch(
            "web_backend.routes.resumes.get_dag_run_status",
            return_value=None,
        ):
            resp = client.get(f"{STATUS_URL}/does_not_exist")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_success_status_mapped(self) -> None:
        fake = DagRunResult(
            dag_id="resume_etl",
            run_id="run_done",
            status=DagRunStatus.SUCCESS,
            conf={},
        )
        with patch(
            "web_backend.routes.resumes.get_dag_run_status",
            return_value=fake,
        ):
            resp = client.get(f"{STATUS_URL}/run_done")

        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_failed_status_mapped(self) -> None:
        fake = DagRunResult(
            dag_id="resume_etl",
            run_id="run_fail",
            status=DagRunStatus.FAILED,
            conf={},
        )
        with patch(
            "web_backend.routes.resumes.get_dag_run_status",
            return_value=fake,
        ):
            resp = client.get(f"{STATUS_URL}/run_fail")

        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"


# ------------------------------------------------------------------ #
#  Dummy Airflow fallback (integration-style)
# ------------------------------------------------------------------ #


class TestDummyAirflowRoundTrip:
    """Exercise the in-memory dummy backend via the API endpoints."""

    def test_upload_then_poll_status(self) -> None:
        """Upload resumes, then poll the returned run_id for status."""
        # Ensure AIRFLOW_BASE_URL is unset so the dummy backend is used
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("AIRFLOW_BASE_URL", None)

            upload_resp = client.post(UPLOAD_URL, json=_resume_payload())

        assert upload_resp.status_code == 200
        run_id = upload_resp.json()["run_id"]

        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("AIRFLOW_BASE_URL", None)

            status_resp = client.get(f"{STATUS_URL}/{run_id}")

        assert status_resp.status_code == 200
        assert status_resp.json()["run_id"] == run_id

