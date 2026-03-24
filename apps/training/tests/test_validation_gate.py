"""Tests for validation gate thresholds."""

from __future__ import annotations

from training.analysis.gate_config import GateConfig
from training.analysis.validation_gate import evaluate_validation_gate


def test_validation_gate_passes_on_good_metrics() -> None:
  """Validation gate passes when both R2 and MAE satisfy thresholds."""
  config = GateConfig(min_r2=0.6, max_mae=20.0)
  result = evaluate_validation_gate({"r2": 0.85, "mae": 8.0}, config)
  assert result["passed"] is True
  assert result["fail_reasons"] == []


def test_validation_gate_fails_on_bad_metrics() -> None:
  """Validation gate fails when either metric violates thresholds."""
  config = GateConfig(min_r2=0.6, max_mae=20.0)
  result = evaluate_validation_gate({"r2": 0.3, "mae": 22.0}, config)
  assert result["passed"] is False
  assert len(result["fail_reasons"]) == 2
