"""Tests for MLflow configuration helper behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from training.analysis.mlflow_config import configure_mlflow_from_env


def test_configure_mlflow_uses_explicit_uri() -> None:
  """Explicit MLFLOW_TRACKING_URI should win over all fallbacks."""
  with patch.dict(
    "os.environ",
    {
      "MLFLOW_TRACKING_URI": "https://example-mlflow.run.app",
      "MLFLOW_TRACKING_URI_FROM_GCP": "true",
    },
    clear=False,
  ):
    with patch("training.analysis.mlflow_config.mlflow") as mock_mlflow:
      with patch("training.analysis.mlflow_config.subprocess.run") as mock_run:
        uri = configure_mlflow_from_env("file:///tmp/mlruns")

  assert uri == "https://example-mlflow.run.app"
  mock_mlflow.set_tracking_uri.assert_called_once_with("https://example-mlflow.run.app")
  mock_run.assert_not_called()


def test_configure_mlflow_resolves_uri_from_gcp() -> None:
  """Gcloud lookup should be used when explicit URI is missing and flag enabled."""
  completed = MagicMock()
  completed.returncode = 0
  completed.stdout = "https://resolved-from-gcp.run.app\n"
  completed.stderr = ""

  with patch.dict(
    "os.environ",
    {
      "MLFLOW_TRACKING_URI": "",
      "MLFLOW_TRACKING_URI_FROM_GCP": "true",
      "MLFLOW_CLOUD_RUN_SERVICE": "mlflow-tracking",
      "MLFLOW_GCP_REGION": "us-east1",
      "MLFLOW_GCP_PROJECT_ID": "ticketforge-488020",
    },
    clear=False,
  ):
    with patch("training.analysis.mlflow_config.mlflow") as mock_mlflow:
      with patch(
        "training.analysis.mlflow_config.subprocess.run",
        return_value=completed,
      ) as mock_run:
        uri = configure_mlflow_from_env("file:///tmp/mlruns")

  assert uri == "https://resolved-from-gcp.run.app"
  mock_mlflow.set_tracking_uri.assert_called_once_with(
    "https://resolved-from-gcp.run.app"
  )
  assert mock_run.call_count == 1


def test_configure_mlflow_uses_default_when_missing() -> None:
  """Provided default URI should be used when env and gcloud lookup are absent."""
  with patch.dict(
    "os.environ",
    {
      "MLFLOW_TRACKING_URI": "",
      "MLFLOW_TRACKING_URI_FROM_GCP": "false",
    },
    clear=False,
  ):
    with patch("training.analysis.mlflow_config.mlflow") as mock_mlflow:
      uri = configure_mlflow_from_env("file:///tmp/mlruns")

  assert uri == "file:///tmp/mlruns"
  mock_mlflow.set_tracking_uri.assert_called_once_with("file:///tmp/mlruns")
