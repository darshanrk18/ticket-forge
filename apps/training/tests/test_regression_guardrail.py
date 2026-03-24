"""Tests for regression guardrail threshold behavior."""

from __future__ import annotations

from training.analysis.regression_guardrail import evaluate_regression_guardrail


def test_guardrail_passes_when_within_threshold() -> None:
  """Guardrail passes when candidate degradation is below threshold."""
  result = evaluate_regression_guardrail(
    candidate_metrics={"mae": 4.2, "rmse": 6.0, "r2": 0.91},
    baseline_metrics={"mae": 4.0, "rmse": 5.9, "r2": 0.92},
    max_allowed_degradation=0.10,
  )
  assert result["passed"] is True


def test_guardrail_blocks_when_over_threshold() -> None:
  """Guardrail blocks when MAE or RMSE degradation exceeds threshold."""
  result = evaluate_regression_guardrail(
    candidate_metrics={"mae": 8.0, "rmse": 9.0, "r2": 0.70},
    baseline_metrics={"mae": 4.0, "rmse": 5.0, "r2": 0.90},
    max_allowed_degradation=0.10,
  )
  assert result["passed"] is False
  assert result["fail_reasons"]


def test_guardrail_passes_without_baseline() -> None:
  """Guardrail allows first deployment when no baseline exists."""
  result = evaluate_regression_guardrail(
    candidate_metrics={"mae": 4.0, "rmse": 6.0, "r2": 0.9},
    baseline_metrics=None,
    max_allowed_degradation=0.10,
  )
  assert result["passed"] is True
  assert result.get("note") == "no-production-baseline"
