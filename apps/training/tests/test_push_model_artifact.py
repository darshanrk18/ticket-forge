"""Tests for push_model_artifact module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import joblib
import pytest
from sklearn.linear_model import LinearRegression

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run_dir(tmp_path: Path, model_name: str = "random_forest") -> Path:
  """Create a minimal run directory with all expected artifact files."""
  run_dir = tmp_path / "test_run"
  run_dir.mkdir()

  # best.txt
  (run_dir / "best.txt").write_text(
    f"Best Model: {model_name}\nR2 Score: 0.9868\n\nAll Metrics:\nmae: 4.2778\n"
  )

  # model pickle
  model = LinearRegression()
  model.fit([[1], [2], [3]], [1, 2, 3])
  joblib.dump(model, run_dir / f"{model_name}.pkl")

  # eval metrics
  (run_dir / f"eval_{model_name}.json").write_text(
    json.dumps({"mae": 4.2778, "mse": 28.06, "rmse": 5.297, "r2": 0.9868})
  )

  # bias report
  (run_dir / f"bias_{model_name}_repo.txt").write_text("Bias report content")

  return run_dir


# ---------------------------------------------------------------------------
# _read_best_model
# ---------------------------------------------------------------------------


class TestReadBestModel:
  def test_reads_model_name_correctly(self, tmp_path: Path) -> None:
    from training.analysis.push_model_artifact import _read_best_model

    run_dir = _make_run_dir(tmp_path)
    assert _read_best_model(run_dir) == "random_forest"

  def test_returns_none_when_best_txt_missing(self, tmp_path: Path) -> None:
    from training.analysis.push_model_artifact import _read_best_model

    run_dir = tmp_path / "empty_run"
    run_dir.mkdir()
    assert _read_best_model(run_dir) is None

  def test_returns_none_when_best_txt_malformed(self, tmp_path: Path) -> None:
    from training.analysis.push_model_artifact import _read_best_model

    run_dir = tmp_path / "bad_run"
    run_dir.mkdir()
    (run_dir / "best.txt").write_text("No model info here")
    assert _read_best_model(run_dir) is None


# ---------------------------------------------------------------------------
# _collect_artifacts
# ---------------------------------------------------------------------------


class TestCollectArtifacts:
  def test_collects_all_expected_files(self, tmp_path: Path) -> None:
    from training.analysis.push_model_artifact import _collect_artifacts

    run_dir = _make_run_dir(tmp_path)
    artifacts = _collect_artifacts(run_dir, "random_forest")

    names = [a.name for a in artifacts]
    assert "random_forest.pkl" in names
    assert "eval_random_forest.json" in names
    assert "bias_random_forest_repo.txt" in names

  def test_skips_missing_files(self, tmp_path: Path) -> None:
    from training.analysis.push_model_artifact import _collect_artifacts

    run_dir = tmp_path / "partial_run"
    run_dir.mkdir()
    (run_dir / "bias_random_forest_repo.txt").write_text("bias")

    artifacts = _collect_artifacts(run_dir, "random_forest")
    assert len(artifacts) == 1
    assert artifacts[0].name == "bias_random_forest_repo.txt"

  def test_collects_multiple_bias_reports(self, tmp_path: Path) -> None:
    from training.analysis.push_model_artifact import _collect_artifacts

    run_dir = _make_run_dir(tmp_path)
    (run_dir / "bias_random_forest_seniority.txt").write_text("bias seniority")

    artifacts = _collect_artifacts(run_dir, "random_forest")
    bias_files = [a for a in artifacts if "bias" in a.name]
    assert len(bias_files) == 2


# ---------------------------------------------------------------------------
# push_model_artifacts
# ---------------------------------------------------------------------------


class TestPushModelArtifacts:
  def test_dry_run_returns_correct_uris(self, tmp_path: Path) -> None:
    from training.analysis.push_model_artifact import push_model_artifacts

    _make_run_dir(tmp_path)

    with patch("training.analysis.push_model_artifact.Paths") as mp:
      mp.models_root = tmp_path
      uris = push_model_artifacts("test_run", dry_run=True)

    assert len(uris) == 4
    assert all(u.startswith("gs://ticketforge-dvc/models/test_run/") for u in uris)

  def test_dry_run_does_not_call_gcs(self, tmp_path: Path) -> None:
    from training.analysis.push_model_artifact import push_model_artifacts

    _make_run_dir(tmp_path)

    with (
      patch("training.analysis.push_model_artifact.Paths") as mp,
      patch("training.analysis.push_model_artifact.storage") as mock_storage,
      patch("training.analysis.push_model_artifact.HAS_GCS", True),
    ):
      mp.models_root = tmp_path
      push_model_artifacts("test_run", dry_run=True)

    mock_storage.Client.assert_not_called()

  def test_raises_when_run_dir_missing(self, tmp_path: Path) -> None:
    from training.analysis.push_model_artifact import push_model_artifacts

    with patch("training.analysis.push_model_artifact.Paths") as mp:
      mp.models_root = tmp_path
      with pytest.raises(FileNotFoundError):
        push_model_artifacts("nonexistent_run", dry_run=True)

  def test_raises_when_no_best_model(self, tmp_path: Path) -> None:
    from training.analysis.push_model_artifact import push_model_artifacts

    run_dir = tmp_path / "no_best"
    run_dir.mkdir()

    with patch("training.analysis.push_model_artifact.Paths") as mp:
      mp.models_root = tmp_path
      with pytest.raises(RuntimeError):
        push_model_artifacts("no_best", dry_run=True)

  def test_writes_manifest_on_real_upload(self, tmp_path: Path) -> None:
    from training.analysis.push_model_artifact import push_model_artifacts

    run_dir = _make_run_dir(tmp_path)

    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with (
      patch("training.analysis.push_model_artifact.Paths") as mp,
      patch("training.analysis.push_model_artifact.storage") as mock_storage,
      patch("training.analysis.push_model_artifact.HAS_GCS", True),
    ):
      mp.models_root = tmp_path
      mock_storage.Client.return_value = mock_client
      push_model_artifacts("test_run")

    manifest_path = run_dir / "artifact_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["best_model"] == "random_forest"
    assert manifest["run_id"] == "test_run"
    assert len(manifest["artifacts"]) == 4

  def test_upload_called_for_each_artifact(self, tmp_path: Path) -> None:
    from training.analysis.push_model_artifact import push_model_artifacts

    _make_run_dir(tmp_path)

    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with (
      patch("training.analysis.push_model_artifact.Paths") as mp,
      patch("training.analysis.push_model_artifact.storage") as mock_storage,
      patch("training.analysis.push_model_artifact.HAS_GCS", True),
    ):
      mp.models_root = tmp_path
      mock_storage.Client.return_value = mock_client
      push_model_artifacts("test_run")

    assert mock_blob.upload_from_filename.call_count == 4
