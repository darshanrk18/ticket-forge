"""Tests for dataset drift comparison helpers."""

from __future__ import annotations

from training.analysis.drift_detection import DriftThresholds, compare_profile_reports


def _profile(
  *,
  row_count: int,
  mean: float,
  std: float,
  failed_expectations: int = 0,
  repo_counts: dict[str, int] | None = None,
) -> dict[str, object]:
  return {
    "dataset": "sample.jsonl",
    "row_count": row_count,
    "numeric_stats": {
      "completion_hours_business": {
        "mean": mean,
        "std": std,
        "min": 1.0,
        "max": 10.0,
        "missing": 0,
      }
    },
    "categorical_stats": {
      "repo": {
        "unique_values": 2,
        "top_values": repo_counts or {"repo-a": row_count},
        "missing": 0,
      }
    },
    "ge_validation": {
      "success": failed_expectations == 0,
      "failed_expectations": failed_expectations,
    },
  }


def test_compare_profile_reports_flags_numeric_and_categorical_drift() -> None:
  """Large distribution shifts should be reported as drift."""
  baseline = _profile(
    row_count=100,
    mean=10.0,
    std=2.0,
    repo_counts={"repo-a": 80, "repo-b": 20},
  )
  current = _profile(
    row_count=160,
    mean=14.0,
    std=3.0,
    failed_expectations=2,
    repo_counts={"repo-a": 40, "repo-b": 120},
  )
  thresholds = DriftThresholds(
    max_row_count_delta_ratio=0.25,
    max_numeric_mean_delta_ratio=0.20,
    max_numeric_std_delta_ratio=0.20,
    max_categorical_distribution_gap=0.20,
    max_failed_expectations_delta=0,
  )

  report = compare_profile_reports(baseline, current, thresholds)

  assert report["drift_detected"] is True
  assert report["row_count"]["drifted"] is True
  assert report["numeric_drift"]["completion_hours_business"]["drifted"] is True
  assert report["categorical_drift"]["repo"]["drifted"] is True
  assert report["validation_drift"]["drifted"] is True
  assert report["breaches"]


def test_compare_profile_reports_accepts_small_changes_within_thresholds() -> None:
  """Small differences should not trigger drift."""
  baseline = _profile(
    row_count=100,
    mean=10.0,
    std=2.0,
    repo_counts={"repo-a": 60, "repo-b": 40},
  )
  current = _profile(
    row_count=108,
    mean=10.8,
    std=2.1,
    repo_counts={"repo-a": 58, "repo-b": 42},
  )

  report = compare_profile_reports(baseline, current, DriftThresholds())

  assert report["drift_detected"] is False
  assert report["breaches"] == []
