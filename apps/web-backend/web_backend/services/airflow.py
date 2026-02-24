"""Airflow REST API client for triggering DAG runs on a remote server.

Calls the Airflow stable REST API (``/api/v1``) on a remote VM.
Falls back to a local in-memory dummy when ``AIRFLOW_BASE_URL`` is not
set so the backend can still be developed without a live Airflow instance.

Required env vars for production:
    AIRFLOW_BASE_URL   - e.g. ``http://airflow-vm:8080``
    AIRFLOW_USERNAME   - HTTP basic-auth username  (default: ``airflow``)
    AIRFLOW_PASSWORD   - HTTP basic-auth password  (default: ``airflow``)
"""

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------- #
#  Data models
# ---------------------------------------------------------------------- #


class DagRunStatus(str, Enum):
    """Possible states of an Airflow DAG run."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class DagRunResult:
    """Result returned after triggering a DAG run."""

    dag_id: str
    run_id: str
    status: DagRunStatus
    conf: Dict[str, Any] = field(default_factory=dict)
    triggered_at: str = ""

    def __post_init__(self) -> None:
        if not self.triggered_at:
            self.triggered_at = datetime.now(tz=UTC).isoformat()


# The DAG id that handles the resume-ingestion cold-start pipeline
RESUME_INGEST_DAG_ID = "resume_etl"


# ---------------------------------------------------------------------- #
#  Remote Airflow REST client
# ---------------------------------------------------------------------- #


def _get_airflow_config() -> tuple[str, str, str] | None:
    """Return (base_url, username, password) or None if not configured."""
    base_url = os.environ.get("AIRFLOW_BASE_URL")
    if not base_url:
        return None
    username = os.environ.get("AIRFLOW_USERNAME", "airflow")
    password = os.environ.get("AIRFLOW_PASSWORD", "airflow")
    return base_url.rstrip("/"), username, password


def _map_airflow_state(state: str) -> DagRunStatus:
    """Map an Airflow state string to our DagRunStatus enum."""
    mapping: Dict[str, DagRunStatus] = {
        "queued": DagRunStatus.QUEUED,
        "running": DagRunStatus.RUNNING,
        "success": DagRunStatus.SUCCESS,
        "failed": DagRunStatus.FAILED,
    }
    return mapping.get(state.lower(), DagRunStatus.QUEUED)


def _remote_trigger_dag(
    dag_id: str,
    conf: Dict[str, Any],
    base_url: str,
    username: str,
    password: str,
) -> DagRunResult:
    """POST to the Airflow REST API to trigger a DAG run."""
    url = f"{base_url}/api/v1/dags/{dag_id}/dagRuns"
    payload: Dict[str, Any] = {"conf": conf}

    resp = httpx.post(
        url,
        json=payload,
        auth=(username, password),
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()

    return DagRunResult(
        dag_id=data.get("dag_id", dag_id),
        run_id=data.get("dag_run_id", ""),
        status=_map_airflow_state(data.get("state", "queued")),
        conf=data.get("conf", conf),
        triggered_at=data.get("execution_date", datetime.now(tz=UTC).isoformat()),
    )


def _remote_get_status(
    dag_id: str,
    run_id: str,
    base_url: str,
    username: str,
    password: str,
) -> DagRunResult | None:
    """GET a DAG run status from the Airflow REST API."""
    url = f"{base_url}/api/v1/dags/{dag_id}/dagRuns/{run_id}"

    resp = httpx.get(
        url,
        auth=(username, password),
        timeout=30.0,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()

    return DagRunResult(
        dag_id=data.get("dag_id", dag_id),
        run_id=data.get("dag_run_id", run_id),
        status=_map_airflow_state(data.get("state", "queued")),
        conf=data.get("conf", {}),
        triggered_at=data.get("execution_date", ""),
    )


# ---------------------------------------------------------------------- #
#  Local in-memory fallback (no Airflow server)
# ---------------------------------------------------------------------- #

_dag_runs: Dict[str, DagRunResult] = {}


def _dummy_trigger_dag(
    dag_id: str,
    conf: Dict[str, Any],
) -> DagRunResult:
    run_id = f"manual__{uuid.uuid4().hex[:12]}"
    result = DagRunResult(
        dag_id=dag_id,
        run_id=run_id,
        status=DagRunStatus.QUEUED,
        conf=conf,
    )
    _dag_runs[run_id] = result
    logger.warning(
        "AIRFLOW_BASE_URL not set — using DUMMY trigger: dag_id=%s  run_id=%s  conf=%s",
        dag_id,
        run_id,
        conf,
    )
    return result


def _dummy_get_status(run_id: str) -> DagRunResult | None:
    return _dag_runs.get(run_id)


# ---------------------------------------------------------------------- #
#  Public API — delegates to remote or dummy automatically
# ---------------------------------------------------------------------- #


def trigger_dag(
    dag_id: str,
    conf: Optional[Dict[str, Any]] = None,
) -> DagRunResult:
    """Trigger an Airflow DAG run.

    Parameters
    ----------
    dag_id:
        The Airflow DAG identifier (e.g. ``resume_ingest_coldstart``).
    conf:
        JSON-serialisable configuration dict forwarded to the DAG run.
    """
    effective_conf = conf or {}
    airflow = _get_airflow_config()

    if airflow is not None:
        base_url, username, password = airflow
        logger.info("Triggering remote DAG %s on %s", dag_id, base_url)
        return _remote_trigger_dag(dag_id, effective_conf, base_url, username, password)

    return _dummy_trigger_dag(dag_id, effective_conf)


def get_dag_run_status(
    run_id: str,
    dag_id: str = RESUME_INGEST_DAG_ID,
) -> DagRunResult | None:
    """Return the status of a previously triggered DAG run.

    Returns ``None`` if the run_id is unknown.
    """
    airflow = _get_airflow_config()

    if airflow is not None:
        base_url, username, password = airflow
        return _remote_get_status(dag_id, run_id, base_url, username, password)

    return _dummy_get_status(run_id)


# ---------------------------------------------------------------------- #
#  Convenience helpers
# ---------------------------------------------------------------------- #


def trigger_resume_ingest_batch(
    resume_items: list[dict[str, Any]],
) -> DagRunResult:
    """Trigger the resume-ingestion pipeline with uploaded resume content.

    Parameters
    ----------
    resume_items:
        A list of dicts, each containing::

            {
                "filename": "john_doe.pdf",
                "content_base64": "<base64-encoded bytes>",
                "github_username": "johndoe",
                "full_name": "John Doe",          # optional
            }
    """
    return trigger_dag(
        dag_id=RESUME_INGEST_DAG_ID,
        conf={"resumes": resume_items},
    )
