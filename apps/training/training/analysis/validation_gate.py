"""Validation gate checks for model CI/CD."""

from __future__ import annotations

from typing import Any

from training.analysis.gate_config import GateConfig


def evaluate_validation_gate(
  metrics: dict[str, float], config: GateConfig
) -> dict[str, Any]:
  """Evaluate candidate metrics against validation thresholds.

  Args:
      metrics: Candidate metrics dictionary.
      config: Loaded gate configuration.

  Returns:
      Validation gate decision payload.
  """
  fail_reasons: list[str] = []

  r2 = float(metrics.get("r2", -1.0))
  mae = float(metrics.get("mae", 1e9))

  if r2 < config.min_r2:
    fail_reasons.append(f"r2-below-threshold:{r2:.4f}<{config.min_r2:.4f}")
  if mae > config.max_mae:
    fail_reasons.append(f"mae-above-threshold:{mae:.4f}>{config.max_mae:.4f}")

  return {
    "passed": len(fail_reasons) == 0,
    "metrics": metrics,
    "thresholds": {
      "min_r2": config.min_r2,
      "max_mae": config.max_mae,
    },
    "fail_reasons": fail_reasons,
  }
