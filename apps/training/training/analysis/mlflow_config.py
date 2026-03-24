"""Helpers to configure MLflow tracking from environment variables.

This module centralizes runtime configuration for MLflow scripts so local and CI
invocations can share a single setup path.
"""

from __future__ import annotations

import subprocess

import mlflow
from shared.configuration import Paths, getenv_or
from shared.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TRACKING_URI = f"file://{Paths.repo_root / 'mlruns'}"


def _is_true(value: str | None) -> bool:
  """Return True when an environment string should be treated as enabled.

  Args:
      value: Raw environment variable value.

  Returns:
      True for common truthy values, else False.
  """
  if value is None:
    return False
  return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_tracking_uri_from_gcp() -> str | None:
  """Resolve Cloud Run URL from gcloud when explicitly enabled.

  Uses these environment variables:
  - ``MLFLOW_TRACKING_URI_FROM_GCP``: set true/1/yes/on to enable lookup.
  - ``MLFLOW_CLOUD_RUN_SERVICE``: Cloud Run service name (default: mlflow-tracking).
  - ``MLFLOW_GCP_REGION``: Cloud Run region (default: us-east1).
  - ``MLFLOW_GCP_PROJECT_ID``: optional project override.

  Returns:
      Resolved Cloud Run URL, or None if lookup is disabled/failed.
  """
  if not _is_true(getenv_or("MLFLOW_TRACKING_URI_FROM_GCP", "false")):
    return None

  service = getenv_or("MLFLOW_CLOUD_RUN_SERVICE", "mlflow-tracking")
  region = getenv_or("MLFLOW_GCP_REGION", "us-east1")
  project = getenv_or("MLFLOW_GCP_PROJECT_ID")

  cmd = [
    "gcloud",
    "run",
    "services",
    "describe",
    service,
    "--region",
    region,
    "--format=value(status.url)",
  ]
  if project:
    cmd.extend(["--project", project])

  result = subprocess.run(cmd, capture_output=True, text=True, check=False)
  if result.returncode != 0:
    logger.warning(
      "Failed to resolve MLFLOW_TRACKING_URI from gcloud: %s",
      result.stderr.strip(),
    )
    return None

  resolved_uri = result.stdout.strip()
  if not resolved_uri:
    logger.warning("gcloud returned empty status.url for MLflow service")
    return None
  return resolved_uri


def configure_mlflow_from_env(default_tracking_uri: str | None = None) -> str:
  """Configure MLflow tracking URI from env and return the resolved URI.

  Resolution order:
  1. ``MLFLOW_TRACKING_URI``
  2. Cloud Run discovery via gcloud when ``MLFLOW_TRACKING_URI_FROM_GCP`` is enabled
  3. ``default_tracking_uri`` argument
  4. local filesystem fallback under ``mlruns/``

  Args:
      default_tracking_uri: Optional caller-provided fallback URI.

  Returns:
      Final tracking URI used by MLflow.
  """
  tracking_uri = getenv_or("MLFLOW_TRACKING_URI")
  if not tracking_uri:
    tracking_uri = _resolve_tracking_uri_from_gcp()
  if not tracking_uri:
    tracking_uri = default_tracking_uri or DEFAULT_TRACKING_URI

  mlflow.set_tracking_uri(tracking_uri)
  logger.info("MLflow tracking URI: %s", tracking_uri)
  return tracking_uri
