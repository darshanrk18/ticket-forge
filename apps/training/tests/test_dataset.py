"""Tests for Dataset class."""

import gzip
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from training.dataset import Dataset

# ---------------------------------------------------------------------------
# Fake pipeline data used across real-data tests
# ---------------------------------------------------------------------------

_EMBEDDING_DIM = 384  # raw embedding size (all-MiniLM-L6-v2)

_NUM_RECORDS = 20


_FAKE_RECORDS = [
  {
    "id": f"hashicorp_terraform-{i}",
    "repo": ["hashicorp/terraform", "ansible/ansible", "prometheus/prometheus"][i % 3],
    "title": f"Issue {i}",
    "body": f"Body {i}",
    "normalized_text": f"normalized {i}",
    "keywords": ["kubernetes", "aws"],
    "embedding": np.random.default_rng(i).random(_EMBEDDING_DIM).tolist(),
    "embedding_model": "all-MiniLM-L6-v2",
    "completion_hours_business": None if i % 5 == 0 else float(i * 10 + 5),
    "assignee": f"engineer_{i}",
    "issue_type": "closed",
    "seniority": "mid",
    "labels": "bug",
    "state": "closed",
    "comments_count": i,
    "historical_avg_completion_hours": float(i * 5),
    "created_at": "2024-01-01T09:00:00Z",
    "assigned_at": "2024-01-01T10:00:00Z",
  }
  for i in range(_NUM_RECORDS)
]


_FAKE_JSONL = "\n".join(json.dumps(r) for r in _FAKE_RECORDS)

_FAKE_WEIGHTS = {
  "group_col": "repo",
  "weights_by_group": {
    "hashicorp/terraform": 0.95,
    "ansible/ansible": 0.61,
    "prometheus/prometheus": 3.20,
  },
}


def _make_fake_pipeline_dir(
  tmp_path: Path,
  dirname: str = "github_issues-2026-02-24T194022Z",
  include_weights: bool = True,
  compressed_dataset: bool = False,
) -> Path:
  """Creates a fake timestamped pipeline output directory."""
  run_dir = tmp_path / dirname
  run_dir.mkdir(parents=True)
  if compressed_dataset:
    with gzip.open(
      run_dir / "tickets_transformed_improved.jsonl.gz", "wt", encoding="utf-8"
    ) as file:
      file.write(_FAKE_JSONL)
  else:
    (run_dir / "tickets_transformed_improved.jsonl").write_text(_FAKE_JSONL)
  if include_weights:
    (run_dir / "sample_weights.json").write_text(json.dumps(_FAKE_WEIGHTS))
  return run_dir


# ---------------------------------------------------------------------------
# Dummy data tests (TRAIN_USE_DUMMY_DATA = True)
# These preserve the original test behaviour.
# ---------------------------------------------------------------------------


class TestDatasetDummyLoading:
  """Tests for Dataset loading with dummy data (original stub behaviour)."""

  def test_load_x_without_subset(self) -> None:
    """Test loading full x dataset without subset."""
    with patch("training.dataset.TRAIN_USE_DUMMY_DATA", True):
      dataset = Dataset(split="train")
      x = dataset.load_x()
    assert x.shape[0] > 0
    assert x.shape[1] > 0
    assert len(x.shape) == 2

  def test_load_y_without_subset(self) -> None:
    """Test loading full y dataset without subset."""
    with patch("training.dataset.TRAIN_USE_DUMMY_DATA", True):
      dataset = Dataset(split="train")
      y = dataset.load_y()
    assert y.shape[0] > 0
    assert len(y.shape) == 1

  def test_load_x_with_subset(self) -> None:
    """Test loading x dataset with subset size."""
    with patch("training.dataset.TRAIN_USE_DUMMY_DATA", True):
      dataset = Dataset(split="train", subset_size=20)
      x = dataset.load_x()
    assert x.shape[0] == 20

  def test_load_y_with_subset(self) -> None:
    """Test loading y dataset with subset size."""
    with patch("training.dataset.TRAIN_USE_DUMMY_DATA", True):
      dataset = Dataset(split="train", subset_size=20)
      y = dataset.load_y()
    assert y.shape[0] == 20

  def test_subset_consistency(self) -> None:
    """Test that x and y subset sizes are consistent."""
    with patch("training.dataset.TRAIN_USE_DUMMY_DATA", True):
      dataset = Dataset(split="train", subset_size=15)
      x = dataset.load_x()
      y = dataset.load_y()
    assert x.shape[0] == y.shape[0] == 15

  def test_as_sklearn_cv_split_without_subset(self) -> None:
    """Test creating sklearn CV split without subset."""
    with patch("training.dataset.TRAIN_USE_DUMMY_DATA", True):
      x, y, cv_split = Dataset.as_sklearn_cv_split()
    assert x.shape[0] == 200  # train + validation (100 + 100)
    assert y.shape[0] == 200
    assert cv_split is not None

  def test_as_sklearn_cv_split_with_subset(self) -> None:
    """Test creating sklearn CV split with subset."""
    with patch("training.dataset.TRAIN_USE_DUMMY_DATA", True):
      x, y, cv_split = Dataset.as_sklearn_cv_split(subset_size=10)
    assert x.shape[0] == 20  # train + validation (10 + 10)
    assert y.shape[0] == 20
    assert cv_split is not None


# ---------------------------------------------------------------------------
# _find_latest_pipeline_output
# ---------------------------------------------------------------------------


class TestFindLatestPipelineOutput:
  def test_picks_most_recent_timestamped_dir(self, tmp_path):
    from training.dataset import find_latest_pipeline_output

    older = tmp_path / "github_issues-2026-02-24T190000Z"
    newer = tmp_path / "github_issues-2026-02-24T200000Z"
    older.mkdir()
    newer.mkdir()
    # Both have the required file — newest should be picked
    (older / "tickets_transformed_improved.jsonl").write_text("{}")
    (newer / "tickets_transformed_improved.jsonl").write_text("{}")

    with patch("training.dataset.Paths") as mock_paths:
      mock_paths.data_root = tmp_path
      result = find_latest_pipeline_output()

    assert result == newer

  def test_skips_incomplete_timestamped_dir(self, tmp_path):
    from training.dataset import find_latest_pipeline_output

    incomplete = tmp_path / "github_issues-2026-02-24T200000Z"
    complete = tmp_path / "github_issues-2026-02-24T190000Z"
    incomplete.mkdir()
    complete.mkdir()
    # Only the older dir has the required file
    (complete / "tickets_transformed_improved.jsonl").write_text("{}")

    with patch("training.dataset.Paths") as mock_paths:
      mock_paths.data_root = tmp_path
      result = find_latest_pipeline_output()

    assert result == complete

  def test_falls_back_to_legacy_dir(self, tmp_path):
    from training.dataset import find_latest_pipeline_output

    legacy = tmp_path / "github_issues"
    legacy.mkdir()
    (legacy / "tickets_transformed_improved.jsonl").write_text("{}")

    with patch("training.dataset.Paths") as mock_paths:
      mock_paths.data_root = tmp_path
      result = find_latest_pipeline_output()

    assert result == legacy

  def test_raises_if_no_dir_found(self, tmp_path):
    from training.dataset import find_latest_pipeline_output

    with patch("training.dataset.Paths") as mock_paths:
      mock_paths.data_root = tmp_path
      with pytest.raises(FileNotFoundError):
        find_latest_pipeline_output()

  def test_respects_dataset_id_override_relative_path(self, tmp_path):
    from training.dataset import find_latest_pipeline_output

    # Create a dataset with explicit name
    dataset = tmp_path / "github_issues-2026-02-24T194022Z"
    dataset.mkdir()
    (dataset / "tickets_transformed_improved.jsonl").write_text("{}")

    # Also create a newer one to ensure override takes precedence
    newer = tmp_path / "github_issues-2026-02-24T200000Z"
    newer.mkdir()
    (newer / "tickets_transformed_improved.jsonl").write_text("{}")

    with (
      patch("training.dataset.Paths") as mock_paths,
      patch("training.dataset.getenv_or") as mock_getenv,
    ):
      mock_paths.data_root = tmp_path
      # Override to use the older dataset
      mock_getenv.return_value = "github_issues-2026-02-24T194022Z"
      result = find_latest_pipeline_output()

    assert result == dataset

  def test_respects_dataset_id_override_absolute_path(self, tmp_path):
    from training.dataset import find_latest_pipeline_output

    dataset = tmp_path / "github_issues-2026-02-24T194022Z"
    dataset.mkdir()
    (dataset / "tickets_transformed_improved.jsonl").write_text("{}")

    with (
      patch("training.dataset.Paths") as mock_paths,
      patch("training.dataset.getenv_or") as mock_getenv,
    ):
      mock_paths.data_root = tmp_path
      # Override with absolute path
      mock_getenv.return_value = str(dataset)
      result = find_latest_pipeline_output()

    assert result == dataset

  def test_raises_on_invalid_dataset_id_override(self, tmp_path):
    from training.dataset import find_latest_pipeline_output

    with (
      patch("training.dataset.Paths") as mock_paths,
      patch("training.dataset.getenv_or") as mock_getenv,
    ):
      mock_paths.data_root = tmp_path
      # Override to non-existent dataset
      mock_getenv.return_value = "github_issues-2026-02-24T999999Z"
      with pytest.raises(FileNotFoundError) as exc_info:
        find_latest_pipeline_output()

      assert "Dataset override" in str(exc_info.value)

  def test_dataset_id_override_missing_required_file(self, tmp_path):
    from training.dataset import find_latest_pipeline_output

    dataset = tmp_path / "github_issues-2026-02-24T194022Z"
    dataset.mkdir()
    # Create directory but without required file

    with (
      patch("training.dataset.Paths") as mock_paths,
      patch("training.dataset.getenv_or") as mock_getenv,
    ):
      mock_paths.data_root = tmp_path
      mock_getenv.return_value = "github_issues-2026-02-24T194022Z"
      with pytest.raises(FileNotFoundError) as exc_info:
        find_latest_pipeline_output()

      assert "Dataset override" in str(exc_info.value)
      assert "missing tickets_transformed_improved.jsonl" in str(exc_info.value)

  def test_accepts_gzip_dataset_override(self, tmp_path):
    from training.dataset import find_latest_pipeline_output

    dataset = _make_fake_pipeline_dir(
      tmp_path,
      dirname="github_issues-2026-02-24T194022Z",
      compressed_dataset=True,
    )

    with (
      patch("training.dataset.Paths") as mock_paths,
      patch("training.dataset.getenv_or") as mock_getenv,
    ):
      mock_paths.data_root = tmp_path
      mock_getenv.return_value = "github_issues-2026-02-24T194022Z"
      result = find_latest_pipeline_output()

    assert result == dataset


# ---------------------------------------------------------------------------
# _split_indices
# ---------------------------------------------------------------------------


class TestSplitIndices:
  def test_splits_are_correct_sizes(self):
    from training.dataset import _split_indices

    n = 100
    assert len(_split_indices(n, "train")) == 70
    assert len(_split_indices(n, "validation")) == 15
    assert len(_split_indices(n, "test")) == 15

  def test_splits_are_non_overlapping(self):
    from training.dataset import _split_indices

    n = 100
    train_idx = set(_split_indices(n, "train"))
    val_idx = set(_split_indices(n, "validation"))
    test_idx = set(_split_indices(n, "test"))

    assert train_idx.isdisjoint(val_idx)
    assert train_idx.isdisjoint(test_idx)
    assert val_idx.isdisjoint(test_idx)

  def test_splits_cover_all_indices(self):
    from training.dataset import _split_indices

    n = 100
    all_idx = (
      set(_split_indices(n, "train"))
      | set(_split_indices(n, "validation"))
      | set(_split_indices(n, "test"))
    )
    assert all_idx == set(range(n))

  def test_splits_are_deterministic(self):
    from training.dataset import _split_indices

    np.testing.assert_array_equal(
      _split_indices(100, "train"),
      _split_indices(100, "train"),
    )


# ---------------------------------------------------------------------------
# Dataset.load_x (real data)
# ---------------------------------------------------------------------------


class TestLoadXRealData:
  def test_returns_correct_embedding_shape(self, tmp_path):
    _make_fake_pipeline_dir(tmp_path)
    with (
      patch("training.dataset.Paths") as mp,
      patch("training.dataset.TRAIN_USE_DUMMY_DATA", False),
    ):
      mp.data_root = tmp_path
      x = Dataset(split="train").load_x()
    assert x.ndim == 2
    assert x.shape[1] >= _EMBEDDING_DIM  # at least embeddings + some features

  def test_subset_size_respected(self, tmp_path):
    _make_fake_pipeline_dir(tmp_path)
    with (
      patch("training.dataset.Paths") as mp,
      patch("training.dataset.TRAIN_USE_DUMMY_DATA", False),
    ):
      mp.data_root = tmp_path
      x = Dataset(split="train", subset_size=3).load_x()
    assert x.shape[0] == 3

  def test_loads_gzip_dataset(self, tmp_path):
    _make_fake_pipeline_dir(tmp_path, compressed_dataset=True)
    with (
      patch("training.dataset.Paths") as mp,
      patch("training.dataset.TRAIN_USE_DUMMY_DATA", False),
    ):
      mp.data_root = tmp_path
      x = Dataset(split="train").load_x()
    assert x.ndim == 2
    assert x.shape[0] > 0


# ---------------------------------------------------------------------------
# Dataset.load_y (real data)
# ---------------------------------------------------------------------------


class TestLoadYRealData:
  def test_returns_1d_array(self, tmp_path):
    _make_fake_pipeline_dir(tmp_path)
    with (
      patch("training.dataset.Paths") as mp,
      patch("training.dataset.TRAIN_USE_DUMMY_DATA", False),
    ):
      mp.data_root = tmp_path
      y = Dataset(split="train").load_y()
    assert y.ndim == 1

  def test_nan_imputation_leaves_no_nans(self, tmp_path):
    _make_fake_pipeline_dir(tmp_path)
    with (
      patch("training.dataset.Paths") as mp,
      patch("training.dataset.TRAIN_USE_DUMMY_DATA", False),
    ):
      mp.data_root = tmp_path
      y = Dataset(split="train").load_y()
    assert not np.isnan(y).any()


# ---------------------------------------------------------------------------
# Dataset.load_metadata (real data)
# ---------------------------------------------------------------------------


class TestLoadMetadataRealData:
  def test_returns_dataframe_with_correct_columns(self, tmp_path):
    _make_fake_pipeline_dir(tmp_path)
    with (
      patch("training.dataset.Paths") as mp,
      patch("training.dataset.TRAIN_USE_DUMMY_DATA", False),
    ):
      mp.data_root = tmp_path
      meta = Dataset(split="train").load_metadata()
    assert isinstance(meta, pd.DataFrame)
    expected_cols = {"repo", "seniority", "labels", "completion_hours_business"}
    assert set(meta.columns) == expected_cols


# ---------------------------------------------------------------------------
# Dataset.load_sample_weights (real data)
# ---------------------------------------------------------------------------


class TestLoadSampleWeightsRealData:
  def test_loads_from_weights_file(self, tmp_path):
    _make_fake_pipeline_dir(tmp_path)
    with (
      patch("training.dataset.Paths") as mp,
      patch("training.dataset.TRAIN_USE_DUMMY_DATA", False),
    ):
      mp.data_root = tmp_path
      ds = Dataset(split="train")
      w = ds.load_sample_weights()
      y = ds.load_y()
    assert w.ndim == 1
    assert len(w) == len(y)

  def test_falls_back_to_inverse_frequency(self, tmp_path):
    _make_fake_pipeline_dir(tmp_path, include_weights=False)
    with (
      patch("training.dataset.Paths") as mp,
      patch("training.dataset.TRAIN_USE_DUMMY_DATA", False),
    ):
      mp.data_root = tmp_path
      w = Dataset(split="train").load_sample_weights()
    assert w.ndim == 1
    assert (w > 0).all()

  def test_weights_same_length_as_y(self, tmp_path):
    _make_fake_pipeline_dir(tmp_path)
    with (
      patch("training.dataset.Paths") as mp,
      patch("training.dataset.TRAIN_USE_DUMMY_DATA", False),
    ):
      mp.data_root = tmp_path
      ds = Dataset(split="train")
      assert len(ds.load_sample_weights()) == len(ds.load_y())
