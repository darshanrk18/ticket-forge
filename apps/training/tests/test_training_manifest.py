"""Tests for training manifest lineage fields."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from training.analysis.run_manifest import (
  create_run_manifest,
  load_manifest,
  update_manifest,
)


def test_manifest_records_cloud_dataset_lineage(tmp_path: Path) -> None:
  """Run manifest persists cloud dataset lineage fields."""
  with patch("training.analysis.run_manifest.Paths") as paths:
    paths.models_root = tmp_path
    create_run_manifest(
      run_id="run-cloud-1",
      trigger_type="push",
      commit_sha="abc",
      snapshot_id="snap",
      source_uri="dvc://data",
    )

    update_manifest(
      "run-cloud-1",
      training_dataset={
        "dataset_source": "cloud_storage",
        "dataset_path": "gs://bucket/datasets/v2/tickets_transformed_improved.jsonl",
        "dataset_version": "v2.0",
        "dataset_id": "dataset-v2",
      },
    )

    manifest = load_manifest("run-cloud-1")

  dataset = manifest.get("training_dataset")
  assert isinstance(dataset, dict)
  assert dataset["dataset_source"] == "cloud_storage"
  assert dataset["dataset_version"] == "v2.0"
