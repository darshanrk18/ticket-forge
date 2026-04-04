"""Tests for train_with_gates CLI behavior."""

from __future__ import annotations

import sys
from unittest.mock import patch

from pytest import raises
from training.cmd.train_with_gates import (
  _parse_args,
  _resolve_data_snapshot,
  _run_training,
)


def test_parse_args_defaults_to_dvc_source_mode() -> None:
  """Parser defaults to dvc source mode."""
  with patch(
    "sys.argv",
    [
      "train_with_gates.py",
      "--runid",
      "run-1",
    ],
  ):
    args = _parse_args()

  assert args.runid == "run-1"
  assert args.source_uri == "dvc"


def test_parse_args_supports_gcs_source_mode() -> None:
  """Parser accepts gcs source mode selector."""
  with patch(
    "sys.argv",
    [
      "train_with_gates.py",
      "--runid",
      "run-2",
      "--source-uri",
      "gcs",
    ],
  ):
    args = _parse_args()

  assert args.runid == "run-2"
  assert args.source_uri == "gcs"


def test_run_training_forwards_cloud_storage_flag_for_gcs_source() -> None:
  """Training subprocess receives cloud mode flag for gcs source."""
  with patch("training.cmd.train_with_gates.subprocess.run") as mock_run:
    _run_training("run-3", source_uri="gcs")

  mock_run.assert_called_once_with(
    [
      sys.executable,
      "-m",
      "training.cmd.train",
      "--runid",
      "run-3",
      "--cloud-storage",
    ],
    check=True,
  )


def test_run_training_uses_local_mode_for_dvc_source() -> None:
  """Training subprocess keeps local mode for dvc source."""
  with patch("training.cmd.train_with_gates.subprocess.run") as mock_run:
    _run_training("run-4", source_uri="dvc")

  mock_run.assert_called_once_with(
    [
      sys.executable,
      "-m",
      "training.cmd.train",
      "--runid",
      "run-4",
    ],
    check=True,
  )


def test_resolve_data_snapshot_for_dvc_source() -> None:
  """DVC source mode resolves manifest snapshot defaults."""
  assert _resolve_data_snapshot("dvc") == ("dvc-latest", "dvc://latest")


def test_resolve_data_snapshot_for_gcs_source_reads_bucket_env() -> None:
  """GCS source mode reads source URI from GCS_BUCKET_NAME."""
  with patch("training.cmd.train_with_gates.getenv_or", return_value="gs://bucket"):
    assert _resolve_data_snapshot("gcs") == ("cloud-index", "gs://bucket")


def test_resolve_data_snapshot_for_gcs_source_requires_bucket_env() -> None:
  """GCS source mode raises when bucket env is missing."""
  with patch("training.cmd.train_with_gates.getenv_or", return_value=None):
    with raises(ValueError, match="GCS_BUCKET_NAME"):
      _resolve_data_snapshot("gcs")
