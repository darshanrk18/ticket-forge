"""Tests for training command module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from training.cmd.train import _load_metrics, _parse_arguments, _save_best_model_info


class TestParseArguments:
  """Tests for _parse_arguments function."""

  def test_parse_arguments_with_custom_models(self) -> None:
    """Test parsing arguments with custom models."""
    with patch("sys.argv", ["train.py", "-m", "forest", "linear"]):
      models, run_id, promote = _parse_arguments()
      assert "forest" in models
      assert "linear" in models

  def test_parse_arguments_with_custom_run_id(self) -> None:
    """Test parsing arguments with custom run_id."""
    with patch("sys.argv", ["train.py", "-r", "test_run_123"]):
      models, run_id, promote = _parse_arguments()
      assert run_id == "test_run_123"

  def test_parse_arguments_promote_defaults_false(self) -> None:
    """Test that --promote defaults to False."""
    with patch("sys.argv", ["train.py"]):
      _models, _run_id, promote = _parse_arguments()
      assert promote is False

  def test_parse_arguments_promote_flag(self) -> None:
    """Test that --promote sets promote to True."""
    with patch("sys.argv", ["train.py", "--promote"]):
      _models, _run_id, promote = _parse_arguments()
      assert promote is True


class TestLoadMetrics:
  """Tests for _load_metrics function."""

  def test_load_metrics_empty_directory(self) -> None:
    """Test loading metrics from empty directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
      run_dir = Path(tmpdir)
      metrics_data, best_models = _load_metrics(run_dir)

      assert metrics_data == {}
      assert best_models == []

  def test_load_metrics_with_single_model(self) -> None:
    """Test loading metrics for a single model."""
    with tempfile.TemporaryDirectory() as tmpdir:
      run_dir = Path(tmpdir)

      test_metrics = {"mae": 1.5, "mse": 2.0, "rmse": 1.4, "r2": 0.95}
      eval_file = run_dir / "eval_forest.json"
      with open(eval_file, "w") as f:
        json.dump(test_metrics, f)

      metrics_data, best_models = _load_metrics(run_dir)

      assert "forest" in metrics_data
      assert len(best_models) == 1


class TestSaveBestModelInfo:
  """Tests for _save_best_model_info function."""

  def test_save_best_model_info_empty_list(self) -> None:
    """Test saving with empty best models list."""
    with tempfile.TemporaryDirectory() as tmpdir:
      run_dir = Path(tmpdir)
      best_models = []
      _save_best_model_info(best_models, run_dir)
      assert not (run_dir / "best.txt").exists()

  def test_save_best_model_info_creates_file(self) -> None:
    """Test that saving best model creates file."""
    with tempfile.TemporaryDirectory() as tmpdir:
      run_dir = Path(tmpdir)
      metrics = {"mae": 1.5, "mse": 2.0, "rmse": 1.4, "r2": 0.95}
      best_models = [("forest", 0.95, metrics)]

      _save_best_model_info(best_models, run_dir)
      best_file = run_dir / "best.txt"
      assert best_file.exists()

  def test_save_best_model_info_selects_best_model(self) -> None:
    """Test that best model with highest R2 is selected."""
    with tempfile.TemporaryDirectory() as tmpdir:
      run_dir = Path(tmpdir)
      best_models = [
        ("linear", 0.85, {"r2": 0.85}),
        ("forest", 0.95, {"r2": 0.95}),
      ]

      _save_best_model_info(best_models, run_dir)
      best_file = run_dir / "best.txt"
      content = best_file.read_text()
      assert "Best Model: forest" in content
