"""Bias gate evaluation for CI/CD model promotion."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from shared.logging import get_logger
from training.analysis.gate_config import GateConfig

logger = get_logger(__name__)

_TRUE_MARKERS = (
  "bias_detected: true",
  "overall_bias_detected: true",
  "bias detected: true",
)


def _extract_relative_gap(text: str) -> float | None:
  """Extract first relative gap percentage-like number from report text."""
  match = re.search(r"relative[_ ]gap[^\d-]*(-?\d+(?:\.\d+)?)", text, re.IGNORECASE)
  if not match:
    return None
  try:
    value = float(match.group(1))
  except ValueError:
    return None
  if value > 1.0:
    return value / 100.0
  return value


def evaluate_bias_gate(
  run_dir: Path,
  model_name: str,
  config: GateConfig,
) -> dict[str, Any]:
  """Evaluate bias artifacts and return pass/fail gate output.

  Args:
      run_dir: Model run directory.
      model_name: Best model identifier.
      config: Gate configuration.

  Returns:
      Bias gate decision payload.
  """
  reports = list(run_dir.glob(f"bias_{model_name}_*.txt"))
  if not reports:
    logger.warning("No bias reports found for model '%s' in %s", model_name, run_dir)
    return {
      "passed": False,
      "slices_evaluated": [],
      "disparities": {},
      "fail_reasons": ["missing-bias-reports"],
    }

  fail_reasons: list[str] = []
  disparities: dict[str, float] = {}
  slices: list[str] = []

  for report in reports:
    slice_name = report.stem.replace(f"bias_{model_name}_", "")
    slices.append(slice_name)
    text = report.read_text(encoding="utf-8", errors="ignore").lower()

    # Check for explicit bias detection marker
    if any(marker in text for marker in _TRUE_MARKERS):
      fail_reasons.append(f"bias-detected:{slice_name}")
      continue

    gap = _extract_relative_gap(text)
    if gap is not None:
      disparities[slice_name] = gap
      if gap > config.max_bias_relative_gap:
        fail_reasons.append(
          f"bias-relative-gap-exceeds-threshold:{slice_name}:{gap:.4f}>{config.max_bias_relative_gap:.4f}"
        )

  return {
    "passed": len(fail_reasons) == 0,
    "slices_evaluated": slices,
    "disparities": disparities,
    "fail_reasons": sorted(set(fail_reasons)),
  }
