"""CLI parsing tests for cloud storage training mode."""

from training.cmd.train import _parse_arguments


def test_parse_arguments_supports_cloud_storage_flags() -> None:
  """CLI parser exposes cloud-storage mode and explicit bucket override."""
  models, run_id, promote, cloud_storage, gcs_bucket = _parse_arguments(
    [
      "--runid",
      "run-1",
      "--cloud-storage",
      "--gcs-bucket",
      "gs://bucket-name",
      "--models",
      "forest",
    ]
  )

  assert run_id == "run-1"
  assert cloud_storage is True
  assert gcs_bucket == "gs://bucket-name"
  assert promote is False
  assert "forest" in models


def test_parse_arguments_default_keeps_local_mode() -> None:
  """CLI parser defaults to local dataset mode when flag is absent."""
  _, _, _, cloud_storage, gcs_bucket = _parse_arguments(["--runid", "run-2"])

  assert cloud_storage is False
  assert gcs_bucket is None
