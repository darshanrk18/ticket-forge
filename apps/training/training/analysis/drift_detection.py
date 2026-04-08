"""Helpers for comparing dataset profile reports and flagging drift."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shared.configuration import getenv_or


@dataclass(slots=True)
class DriftThresholds:
  """Thresholds that decide when a profile comparison counts as drift."""

  max_row_count_delta_ratio: float = 0.25
  max_numeric_mean_delta_ratio: float = 0.20
  max_numeric_std_delta_ratio: float = 0.25
  max_categorical_distribution_gap: float = 0.20
  max_failed_expectations_delta: int = 0

  def to_dict(self) -> dict[str, float | int]:
    """Return a JSON-serializable representation of the thresholds."""
    return asdict(self)


def load_drift_thresholds() -> DriftThresholds:
  """Load drift thresholds from environment variables."""

  def getf(key: str, default: str) -> float:
    return float(getenv_or(key, default) or default)

  def geti(key: str, default: str) -> int:
    return int(getenv_or(key, default) or default)

  return DriftThresholds(
    max_row_count_delta_ratio=getf("MODEL_MONITOR_MAX_ROW_COUNT_DELTA_RATIO", "0.25"),
    max_numeric_mean_delta_ratio=getf(
      "MODEL_MONITOR_MAX_NUMERIC_MEAN_DELTA_RATIO", "0.20"
    ),
    max_numeric_std_delta_ratio=getf(
      "MODEL_MONITOR_MAX_NUMERIC_STD_DELTA_RATIO", "0.25"
    ),
    max_categorical_distribution_gap=getf(
      "MODEL_MONITOR_MAX_CATEGORICAL_DISTRIBUTION_GAP", "0.20"
    ),
    max_failed_expectations_delta=geti(
      "MODEL_MONITOR_MAX_FAILED_EXPECTATIONS_DELTA", "0"
    ),
  )


def _safe_float(value: object, default: float = 0.0) -> float:
  """Convert JSON-ish values into floats."""
  if isinstance(value, int | float):
    return float(value)
  return default


def _safe_int(value: object, default: int = 0) -> int:
  """Convert JSON-ish values into ints."""
  if isinstance(value, bool):
    return int(value)
  if isinstance(value, int):
    return value
  if isinstance(value, float):
    return int(value)
  return default


def _relative_delta(current: float, baseline: float) -> float:
  """Return absolute relative delta, handling zero baselines."""
  if baseline == 0:
    return 0.0 if current == 0 else 1.0
  return abs(current - baseline) / abs(baseline)


def _normalize_top_values(values: object, row_count: int) -> dict[str, float]:
  """Convert categorical top-value counts into approximate proportions."""
  if not isinstance(values, dict) or row_count <= 0:
    return {}

  distribution: dict[str, float] = {}
  for key, value in values.items():
    if isinstance(value, int | float):
      distribution[str(key)] = float(value) / row_count
  return distribution


def _build_row_count_result(
  baseline_row_count: int,
  current_row_count: int,
  thresholds: DriftThresholds,
) -> tuple[dict[str, int | float | bool], list[str]]:
  """Compare dataset sizes and return the row-count section plus breaches."""
  row_count_delta_ratio = _relative_delta(current_row_count, baseline_row_count)
  result: dict[str, int | float | bool] = {
    "baseline": baseline_row_count,
    "current": current_row_count,
    "delta_ratio": round(row_count_delta_ratio, 6),
    "drifted": row_count_delta_ratio > thresholds.max_row_count_delta_ratio,
  }
  breaches: list[str] = []
  if result["drifted"]:
    breaches.append(
      "row_count_delta_ratio:"
      f"{row_count_delta_ratio:.4f}>{thresholds.max_row_count_delta_ratio:.4f}"
    )
  return result, breaches


def _compare_numeric_drift(
  baseline_numeric: object,
  current_numeric: object,
  thresholds: DriftThresholds,
) -> tuple[dict[str, dict[str, float | bool]], list[str]]:
  """Compare numeric profile statistics shared across both reports."""
  breaches: list[str] = []
  results: dict[str, dict[str, float | bool]] = {}
  if not isinstance(baseline_numeric, dict) or not isinstance(current_numeric, dict):
    return results, breaches

  for column in sorted(set(baseline_numeric) & set(current_numeric)):
    baseline_column = baseline_numeric.get(column)
    current_column = current_numeric.get(column)
    if not isinstance(baseline_column, dict) or not isinstance(current_column, dict):
      continue

    mean_delta_ratio = _relative_delta(
      _safe_float(current_column.get("mean")),
      _safe_float(baseline_column.get("mean")),
    )
    std_delta_ratio = _relative_delta(
      _safe_float(current_column.get("std")),
      _safe_float(baseline_column.get("std")),
    )
    drifted = (
      mean_delta_ratio > thresholds.max_numeric_mean_delta_ratio
      or std_delta_ratio > thresholds.max_numeric_std_delta_ratio
    )
    results[column] = {
      "mean_delta_ratio": round(mean_delta_ratio, 6),
      "std_delta_ratio": round(std_delta_ratio, 6),
      "drifted": drifted,
    }
    if mean_delta_ratio > thresholds.max_numeric_mean_delta_ratio:
      breaches.append(
        "numeric_mean_delta_ratio:"
        f"{column}:{mean_delta_ratio:.4f}"
        f">{thresholds.max_numeric_mean_delta_ratio:.4f}"
      )
    if std_delta_ratio > thresholds.max_numeric_std_delta_ratio:
      breaches.append(
        "numeric_std_delta_ratio:"
        f"{column}:{std_delta_ratio:.4f}"
        f">{thresholds.max_numeric_std_delta_ratio:.4f}"
      )

  return results, breaches


def _compare_categorical_drift(
  baseline_categorical: object,
  current_categorical: object,
  *,
  baseline_row_count: int,
  current_row_count: int,
  thresholds: DriftThresholds,
) -> tuple[dict[str, dict[str, float | bool]], list[str]]:
  """Compare categorical top-value distributions shared across both reports."""
  breaches: list[str] = []
  results: dict[str, dict[str, float | bool]] = {}
  if not isinstance(baseline_categorical, dict) or not isinstance(
    current_categorical, dict
  ):
    return results, breaches

  for column in sorted(set(baseline_categorical) & set(current_categorical)):
    baseline_column = baseline_categorical.get(column)
    current_column = current_categorical.get(column)
    if not isinstance(baseline_column, dict) or not isinstance(current_column, dict):
      continue

    baseline_distribution = _normalize_top_values(
      baseline_column.get("top_values"),
      baseline_row_count,
    )
    current_distribution = _normalize_top_values(
      current_column.get("top_values"),
      current_row_count,
    )
    keys = sorted(set(baseline_distribution) | set(current_distribution))
    max_gap = max(
      (
        abs(current_distribution.get(key, 0.0) - baseline_distribution.get(key, 0.0))
        for key in keys
      ),
      default=0.0,
    )
    drifted = max_gap > thresholds.max_categorical_distribution_gap
    results[column] = {
      "max_distribution_gap": round(max_gap, 6),
      "drifted": drifted,
    }
    if drifted:
      breaches.append(
        "categorical_distribution_gap:"
        f"{column}:{max_gap:.4f}"
        f">{thresholds.max_categorical_distribution_gap:.4f}"
      )

  return results, breaches


def _compare_validation_drift(
  baseline_validation: object,
  current_validation: object,
  thresholds: DriftThresholds,
) -> tuple[dict[str, int | bool], list[str]]:
  """Compare Great Expectations failures between baseline and current profiles."""
  baseline_failed = 0
  current_failed = 0
  if isinstance(baseline_validation, dict):
    baseline_failed = _safe_int(baseline_validation.get("failed_expectations"))
  if isinstance(current_validation, dict):
    current_failed = _safe_int(current_validation.get("failed_expectations"))

  failed_expectations_delta = current_failed - baseline_failed
  result: dict[str, int | bool] = {
    "baseline_failed_expectations": baseline_failed,
    "current_failed_expectations": current_failed,
    "failed_expectations_delta": failed_expectations_delta,
    "drifted": failed_expectations_delta > thresholds.max_failed_expectations_delta,
  }
  breaches: list[str] = []
  if result["drifted"]:
    breaches.append(
      "failed_expectations_delta:"
      f"{failed_expectations_delta}>{thresholds.max_failed_expectations_delta}"
    )
  return result, breaches


def compare_profile_reports(
  baseline_profile: dict[str, Any],
  current_profile: dict[str, Any],
  thresholds: DriftThresholds,
) -> dict[str, Any]:
  """Compare two data profile reports and flag threshold breaches."""
  baseline_row_count = _safe_int(baseline_profile.get("row_count"))
  current_row_count = _safe_int(current_profile.get("row_count"))
  row_count_result, row_count_breaches = _build_row_count_result(
    baseline_row_count,
    current_row_count,
    thresholds,
  )
  numeric_results, numeric_breaches = _compare_numeric_drift(
    baseline_profile.get("numeric_stats", {}),
    current_profile.get("numeric_stats", {}),
    thresholds,
  )
  categorical_results, categorical_breaches = _compare_categorical_drift(
    baseline_profile.get("categorical_stats", {}),
    current_profile.get("categorical_stats", {}),
    baseline_row_count=baseline_row_count,
    current_row_count=current_row_count,
    thresholds=thresholds,
  )
  validation_result, validation_breaches = _compare_validation_drift(
    baseline_profile.get("ge_validation", {}),
    current_profile.get("ge_validation", {}),
    thresholds,
  )
  breaches = [
    *row_count_breaches,
    *numeric_breaches,
    *categorical_breaches,
    *validation_breaches,
  ]

  return {
    "generated_at": datetime.now(tz=UTC).isoformat(),
    "baseline_dataset": baseline_profile.get("dataset"),
    "current_dataset": current_profile.get("dataset"),
    "thresholds": thresholds.to_dict(),
    "row_count": row_count_result,
    "numeric_drift": numeric_results,
    "categorical_drift": categorical_results,
    "validation_drift": validation_result,
    "breaches": breaches,
    "drift_detected": bool(breaches),
  }


def write_drift_report(path: str | Path, report: dict[str, Any]) -> Path:
  """Write a drift report to disk."""
  report_path = Path(path)
  report_path.parent.mkdir(parents=True, exist_ok=True)
  with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
  return report_path
