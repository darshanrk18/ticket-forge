"""Regression guardrail checks for candidate-vs-baseline comparisons."""

from __future__ import annotations

from typing import Any


def _relative_degradation(
  candidate: float,
  baseline: float,
  *,
  higher_is_better: bool,
) -> float:
  """Compute relative degradation for a candidate metric."""
  if baseline == 0:
    return 0.0
  if higher_is_better:
    return (baseline - candidate) / abs(baseline)
  return (candidate - baseline) / abs(baseline)


def evaluate_regression_guardrail(
  candidate_metrics: dict[str, float],
  baseline_metrics: dict[str, float] | None,
  max_allowed_degradation: float,
) -> dict[str, Any]:
  """Evaluate whether candidate significantly regresses vs production baseline.

  Args:
      candidate_metrics: Candidate metrics from eval file.
      baseline_metrics: Baseline production metrics if available.
      max_allowed_degradation: Relative regression threshold.

  Returns:
      Guardrail decision payload.
  """
  if not baseline_metrics:
    return {
      "passed": True,
      "max_allowed_degradation": max_allowed_degradation,
      "metric_deltas": {},
      "fail_reasons": [],
      "note": "no-production-baseline",
    }

  metric_deltas: dict[str, float] = {}
  fail_reasons: list[str] = []

  for metric, higher_is_better in (("mae", False), ("rmse", False), ("r2", True)):
    if metric not in candidate_metrics or metric not in baseline_metrics:
      continue
    delta = _relative_degradation(
      float(candidate_metrics[metric]),
      float(baseline_metrics[metric]),
      higher_is_better=higher_is_better,
    )
    metric_deltas[metric] = delta
    if delta > max_allowed_degradation:
      fail_reasons.append(
        f"degradation-exceeds-threshold:{metric}:{delta:.4f}>{max_allowed_degradation:.4f}"
      )

  return {
    "passed": len(fail_reasons) == 0,
    "max_allowed_degradation": max_allowed_degradation,
    "metric_deltas": metric_deltas,
    "fail_reasons": fail_reasons,
  }
