"""Tests for promotion run metadata logging in MLflow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("mlflow")

from training.analysis.mlflow_tracking import _register_model


def test_register_model_logs_eval_metrics() -> None:
  """Promotion run logs eval metrics for future baseline comparisons."""
  fake_model = MagicMock()

  with patch("training.analysis.mlflow_tracking.mlflow") as mock_mlflow:
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=MagicMock())
    ctx.__exit__ = MagicMock(return_value=False)
    mock_mlflow.start_run.return_value = ctx

    ok = _register_model(
      model=fake_model,
      best_model_name="forest",
      run_id="run-1",
      candidate_metrics={"mae": 4.0, "rmse": 6.0, "r2": 0.9},
    )

  assert ok is True
  mock_mlflow.log_metrics.assert_called_once()
