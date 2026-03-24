"""Tests for MLflow experiment tracking and model promotion."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import joblib
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import RandomizedSearchCV

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _make_grid_pickle(directory: Path, model_name: str) -> Path:
  """Train a tiny GridSearch and pickle it; return the pickle path."""
  x = np.random.default_rng(0).random((20, 4))
  y = np.random.default_rng(0).random(20)
  grid = RandomizedSearchCV(
    LinearRegression(),
    param_distributions={"fit_intercept": [True, False]},
    n_iter=2,
    cv=2,
    scoring="neg_mean_squared_error",
    random_state=0,
  )
  grid.fit(x, y)
  path = directory / f"{model_name}.pkl"
  joblib.dump(grid, path)
  return path


def _make_cv_results(directory: Path, model_name: str) -> Path:
  """Write a minimal cv_results JSON and return its path."""
  data = {
    "param_fit_intercept": [True, False],
    "mean_test_score": [-5.0, -8.0],
    "rank_test_score": [1, 2],
  }
  path = directory / f"cv_results_{model_name}.json"
  path.write_text(json.dumps(data))
  return path


def _make_eval_json(directory: Path, model_name: str) -> Path:
  """Write a minimal eval JSON and return its path."""
  data = {"mae": 1.0, "mse": 2.0, "rmse": 1.4, "r2": 0.9}
  path = directory / f"eval_{model_name}.json"
  path.write_text(json.dumps(data))
  return path


def _make_best_txt(directory: Path, model_name: str) -> Path:
  """Write a best.txt pointing at model_name."""
  path = directory / "best.txt"
  path.write_text(f"Best Model: {model_name}\nR2 Score: 0.9000\n")
  return path


def _make_full_run_dir(tmp_path: Path, model_name: str = "forest") -> Path:
  """Create a run dir with all expected artifacts for a single model."""
  run_id = "test_run"
  run_dir = tmp_path / run_id
  run_dir.mkdir()
  _make_grid_pickle(run_dir, model_name)
  _make_cv_results(run_dir, model_name)
  _make_eval_json(run_dir, model_name)
  _make_best_txt(run_dir, model_name)
  return run_dir


def _make_reusable_ctx(run_id: str = "mock-run-id") -> MagicMock:
  """Return a context manager mock reusable across unlimited start_run calls."""
  run = MagicMock()
  run.info.run_id = run_id
  ctx = MagicMock()
  ctx.__enter__ = MagicMock(return_value=run)
  ctx.__exit__ = MagicMock(return_value=False)
  return ctx


# ---------------------------------------------------------------------------
# _log_trial_runs
# ---------------------------------------------------------------------------


class TestLogTrialRuns:
  def test_skips_when_cv_results_missing(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import _log_trial_runs

    missing = tmp_path / "cv_results_nonexistent.json"
    # Should not raise even when file is absent
    with patch("training.analysis.mlflow_tracking.mlflow"):
      _log_trial_runs("parent-run-id", "forest", missing)

  def test_logs_one_run_per_trial(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import _log_trial_runs

    cv_path = _make_cv_results(tmp_path, "forest")

    with patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow:
      mock_mlflow.start_run.return_value = _make_reusable_ctx()
      _log_trial_runs("parent-run-id", "forest", cv_path)

    # Two trials → two start_run calls
    assert mock_mlflow.start_run.call_count == 2

  def test_logs_params_and_metrics_per_trial(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import _log_trial_runs

    cv_path = _make_cv_results(tmp_path, "forest")

    with patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow:
      mock_mlflow.start_run.return_value = _make_reusable_ctx()
      _log_trial_runs("parent-run-id", "forest", cv_path)

    # log_params called once per trial
    assert mock_mlflow.log_params.call_count == 2
    # log_metric called at least mean_test_score + cv_mse per trial
    assert mock_mlflow.log_metric.call_count >= 4

  def test_trial_runs_tagged_with_parent_run_id(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import _log_trial_runs

    cv_path = _make_cv_results(tmp_path, "xgboost")

    with patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow:
      mock_mlflow.start_run.return_value = _make_reusable_ctx()
      _log_trial_runs("my-parent-id", "xgboost", cv_path)

    for c in mock_mlflow.start_run.call_args_list:
      tags = c.kwargs.get("tags", {})
      assert tags.get("mlflow.parentRunId") == "my-parent-id"


# ---------------------------------------------------------------------------
# _log_model_run
# ---------------------------------------------------------------------------


class TestLogModelRun:
  def test_logs_test_metrics_when_eval_exists(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import _log_model_run

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _make_eval_json(run_dir, "forest")
    _make_grid_pickle(run_dir, "forest")
    _make_cv_results(run_dir, "forest")

    with patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow:
      mock_mlflow.start_run.return_value = _make_reusable_ctx("child-run-id")
      _log_model_run("parent-id", "run_001", "forest", run_dir)

    mock_mlflow.log_metrics.assert_called_once()

  def test_sensitivity_plots_logged_when_present(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import _log_model_run

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _make_eval_json(run_dir, "forest")
    _make_grid_pickle(run_dir, "forest")
    _make_cv_results(run_dir, "forest")
    (run_dir / "hyperparam_sensitivity_forest.png").write_bytes(b"fake-png")
    (run_dir / "shap_importance_forest.png").write_bytes(b"fake-png")

    with patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow:
      mock_mlflow.start_run.return_value = _make_reusable_ctx("child-run-id")
      _log_model_run("parent-id", "run_001", "forest", run_dir)

    artifact_calls = mock_mlflow.log_artifact.call_args_list
    logged_names = [Path(c.args[0]).name for c in artifact_calls]
    assert "hyperparam_sensitivity_forest.png" in logged_names
    assert "shap_importance_forest.png" in logged_names

  def test_no_crash_when_eval_missing(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import _log_model_run

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _make_grid_pickle(run_dir, "forest")

    with patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow:
      mock_mlflow.start_run.return_value = _make_reusable_ctx("child-run-id")
      # Should not raise
      _log_model_run("parent-id", "run_001", "forest", run_dir)

  def test_bias_reports_logged(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import _log_model_run

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _make_eval_json(run_dir, "forest")
    _make_grid_pickle(run_dir, "forest")
    _make_cv_results(run_dir, "forest")
    (run_dir / "bias_forest_repo.txt").write_text("bias report")

    with patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow:
      mock_mlflow.start_run.return_value = _make_reusable_ctx("child-run-id")
      _log_model_run("parent-id", "run_001", "forest", run_dir)

    artifact_calls = mock_mlflow.log_artifact.call_args_list
    bias_calls = [c for c in artifact_calls if "bias" in c.args[0]]
    assert len(bias_calls) == 1


# ---------------------------------------------------------------------------
# log_run_to_mlflow
# ---------------------------------------------------------------------------


class TestLogRunToMlflow:
  def test_no_op_when_dummy_data(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import log_run_to_mlflow

    with (
      patch("training.analysis.mlflow_tracking.TRAIN_USE_DUMMY_DATA", True),
      patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow,
    ):
      result = log_run_to_mlflow("any_run_id")

    assert result is None
    mock_mlflow.start_run.assert_not_called()

  def test_returns_none_when_run_dir_missing(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import log_run_to_mlflow

    with (
      patch("training.analysis.mlflow_tracking.TRAIN_USE_DUMMY_DATA", False),
      patch("training.analysis.mlflow_tracking.Paths") as mp,
      patch("training.analysis.mlflow_tracking._setup_experiment"),
    ):
      mp.models_root = tmp_path
      result = log_run_to_mlflow("nonexistent_run")

    assert result is None

  def test_returns_none_when_no_pickles(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import log_run_to_mlflow

    run_dir = tmp_path / "empty_run"
    run_dir.mkdir()

    with (
      patch("training.analysis.mlflow_tracking.TRAIN_USE_DUMMY_DATA", False),
      patch("training.analysis.mlflow_tracking.Paths") as mp,
      patch("training.analysis.mlflow_tracking._setup_experiment"),
    ):
      mp.models_root = tmp_path
      result = log_run_to_mlflow("empty_run")

    assert result is None

  def test_returns_parent_run_id_on_success(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import log_run_to_mlflow

    run_dir = _make_full_run_dir(tmp_path)
    run_id = run_dir.name

    # Use return_value (not side_effect list) so the same context is returned
    # for all start_run calls: parent + search_forest + trial_000 + trial_001
    parent_ctx = _make_reusable_ctx("parent-mlflow-id")

    with (
      patch("training.analysis.mlflow_tracking.TRAIN_USE_DUMMY_DATA", False),
      patch("training.analysis.mlflow_tracking.Paths") as mp,
      patch("training.analysis.mlflow_tracking._setup_experiment"),
      patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow,
      patch("training.analysis.mlflow_tracking.joblib"),
    ):
      mp.models_root = tmp_path
      mock_mlflow.start_run.return_value = parent_ctx
      result = log_run_to_mlflow(run_id)

    assert result == "parent-mlflow-id"

  def test_performance_png_logged_when_present(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import log_run_to_mlflow

    run_dir = _make_full_run_dir(tmp_path)
    (run_dir / "performance.png").write_bytes(b"fake-png")
    run_id = run_dir.name

    # Same fix: return_value handles all 4 start_run calls
    with (
      patch("training.analysis.mlflow_tracking.TRAIN_USE_DUMMY_DATA", False),
      patch("training.analysis.mlflow_tracking.Paths") as mp,
      patch("training.analysis.mlflow_tracking._setup_experiment"),
      patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow,
      patch("training.analysis.mlflow_tracking.joblib"),
    ):
      mp.models_root = tmp_path
      mock_mlflow.start_run.return_value = _make_reusable_ctx("parent-id")
      log_run_to_mlflow(run_id)

    artifact_calls = mock_mlflow.log_artifact.call_args_list
    logged_names = [Path(c.args[0]).name for c in artifact_calls]
    assert "performance.png" in logged_names


# ---------------------------------------------------------------------------
# promote_best_model
# ---------------------------------------------------------------------------


class TestPromoteBestModel:
  def test_no_op_when_dummy_data(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import promote_best_model

    with (
      patch("training.analysis.mlflow_tracking.TRAIN_USE_DUMMY_DATA", True),
      patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow,
    ):
      result = promote_best_model("any_run_id")

    assert result is None
    mock_mlflow.start_run.assert_not_called()

  def test_returns_none_when_best_txt_missing(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import promote_best_model

    run_dir = tmp_path / "run_no_best"
    run_dir.mkdir()

    with (
      patch("training.analysis.mlflow_tracking.TRAIN_USE_DUMMY_DATA", False),
      patch("training.analysis.mlflow_tracking.Paths") as mp,
    ):
      mp.models_root = tmp_path
      result = promote_best_model("run_no_best")

    assert result is None

  def test_returns_none_when_best_txt_malformed(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import promote_best_model

    run_dir = tmp_path / "run_bad"
    run_dir.mkdir()
    (run_dir / "best.txt").write_text("no model info here\n")

    with (
      patch("training.analysis.mlflow_tracking.TRAIN_USE_DUMMY_DATA", False),
      patch("training.analysis.mlflow_tracking.Paths") as mp,
    ):
      mp.models_root = tmp_path
      result = promote_best_model("run_bad")

    assert result is None

  def test_returns_none_when_pickle_missing(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import promote_best_model

    run_dir = tmp_path / "run_no_pkl"
    run_dir.mkdir()
    _make_best_txt(run_dir, "forest")

    with (
      patch("training.analysis.mlflow_tracking.TRAIN_USE_DUMMY_DATA", False),
      patch("training.analysis.mlflow_tracking.Paths") as mp,
      patch("training.analysis.mlflow_tracking._setup_experiment"),
      patch("training.analysis.mlflow_tracking.MlflowClient"),
    ):
      mp.models_root = tmp_path
      result = promote_best_model("run_no_pkl")

    assert result is None

  def test_archives_old_production_before_promoting(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import promote_best_model

    run_dir = _make_full_run_dir(tmp_path)
    run_id = run_dir.name

    old_mv = MagicMock()
    old_mv.current_stage = "Production"
    old_mv.version = "1"

    new_mv = MagicMock()
    new_mv.version = "2"

    mock_client = MagicMock()
    mock_client.get_latest_versions.return_value = [new_mv]
    mock_client.search_model_versions.return_value = [old_mv]

    with (
      patch("training.analysis.mlflow_tracking.TRAIN_USE_DUMMY_DATA", False),
      patch("training.analysis.mlflow_tracking.Paths") as mp,
      patch("training.analysis.mlflow_tracking._setup_experiment"),
      patch("training.analysis.mlflow_tracking.MlflowClient", return_value=mock_client),
      patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow,
    ):
      mp.models_root = tmp_path
      mock_mlflow.start_run.return_value = _make_reusable_ctx()
      result = promote_best_model(run_id)

    mock_client.transition_model_version_stage.assert_any_call(
      name="ticket-forge-best",
      version="1",
      stage="Archived",
    )
    mock_client.transition_model_version_stage.assert_any_call(
      name="ticket-forge-best",
      version="2",
      stage="Production",
    )
    assert result == "2"

  def test_returns_new_version_string(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import promote_best_model

    run_dir = _make_full_run_dir(tmp_path)
    run_id = run_dir.name

    new_mv = MagicMock()
    new_mv.version = "5"

    mock_client = MagicMock()
    mock_client.get_latest_versions.return_value = [new_mv]
    mock_client.search_model_versions.return_value = []

    with (
      patch("training.analysis.mlflow_tracking.TRAIN_USE_DUMMY_DATA", False),
      patch("training.analysis.mlflow_tracking.Paths") as mp,
      patch("training.analysis.mlflow_tracking._setup_experiment"),
      patch("training.analysis.mlflow_tracking.MlflowClient", return_value=mock_client),
      patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow,
    ):
      mp.models_root = tmp_path
      mock_mlflow.start_run.return_value = _make_reusable_ctx()
      result = promote_best_model(run_id)

    assert result == "5"

  def test_returns_none_when_registry_returns_no_versions(self, tmp_path: Path) -> None:
    from training.analysis.mlflow_tracking import promote_best_model

    run_dir = _make_full_run_dir(tmp_path)
    run_id = run_dir.name

    mock_client = MagicMock()
    mock_client.get_latest_versions.return_value = []

    with (
      patch("training.analysis.mlflow_tracking.TRAIN_USE_DUMMY_DATA", False),
      patch("training.analysis.mlflow_tracking.Paths") as mp,
      patch("training.analysis.mlflow_tracking._setup_experiment"),
      patch("training.analysis.mlflow_tracking.MlflowClient", return_value=mock_client),
      patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow,
    ):
      mp.models_root = tmp_path
      mock_mlflow.start_run.return_value = _make_reusable_ctx()
      result = promote_best_model(run_id)

    assert result is None
