"""Tests for run manifest serialization and update behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from training.analysis.run_manifest import (
  create_run_manifest,
  load_manifest,
  update_manifest,
)


def test_create_run_manifest_has_required_sections(tmp_path: Path) -> None:
  """Manifest includes required sections and run identifiers."""
  with patch("training.analysis.run_manifest.Paths") as paths:
    paths.models_root = tmp_path
    path = create_run_manifest(
      run_id="run-123",
      trigger_type="push",
      commit_sha="abc",
      snapshot_id="dvc-latest",
      source_uri="dvc://data",
    )

    manifest = load_manifest("run-123")

  pipeline_run = manifest.get("pipeline_run")
  assert isinstance(pipeline_run, dict)

  assert path.exists()
  assert pipeline_run["run_id"] == "run-123"
  assert "data_snapshot" in manifest
  assert "promotion_decision" in manifest


def test_update_manifest_replaces_sections(tmp_path: Path) -> None:
  """Manifest updates replace top-level sections deterministically."""
  with patch("training.analysis.run_manifest.Paths") as paths:
    paths.models_root = tmp_path
    create_run_manifest("run-123", "push", "abc", "snap", "dvc://data")
    update_manifest("run-123", validation_report={"passed": True})
    manifest = load_manifest("run-123")

  validation_report = manifest.get("validation_report")
  assert isinstance(validation_report, dict)

  assert validation_report["passed"] is True
