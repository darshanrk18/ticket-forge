"""Anomaly detection for data quality monitoring."""

from typing import Any

import numpy as np
import pandas as pd


class AnomalyDetector:
  """Detect data quality anomalies."""

  def __init__(self, outlier_threshold: float = 3.0) -> None:
    """Initialize anomaly detector.

    Args:
        outlier_threshold: Number of standard deviations for outlier detection
    """
    self.outlier_threshold = outlier_threshold

  def detect_missing_values(self, data: pd.DataFrame) -> dict[str, Any]:
    """Detect missing values in dataset.

    Args:
        data: Input DataFrame

    Returns:
        Dictionary with missing value analysis
    """
    total_rows = len(data)
    missing_counts = data.isnull().sum()
    missing_pct = (missing_counts / total_rows * 100).round(2)

    problematic_cols = missing_pct[missing_pct > 5].to_dict()

    return {
      "total_rows": total_rows,
      "columns_with_missing": dict(missing_counts[missing_counts > 0]),
      "missing_percentages": missing_pct[missing_pct > 0].to_dict(),
      "problematic_columns": problematic_cols,
      "has_issues": len(problematic_cols) > 0,
    }

  def detect_outliers(self, data: pd.DataFrame, column: str) -> dict[str, Any]:
    """Detect outliers using z-score method.

    Args:
        data: Input DataFrame
        column: Column to check for outliers

    Returns:
        Dictionary with outlier analysis
    """
    if column not in data.columns:
      return {"error": "Column not found"}

    values = data[column].dropna()

    if len(values) == 0:
      return {"error": "No valid values"}

    mean = values.mean()
    std = values.std()

    if std == 0:
      return {"outliers": [], "count": 0, "indices": []}

    z_scores = np.abs((values - mean) / std)
    outliers = values[z_scores > self.outlier_threshold]

    return {
      "column": column,
      "mean": round(mean, 2),
      "std": round(std, 2),
      "threshold": self.outlier_threshold,
      "outlier_count": len(outliers),
      "outlier_percentage": round(len(outliers) / len(values) * 100, 2),
      "outlier_indices": list(outliers.index)[:10],  # type: ignore[attr-defined,arg-type]
      "has_issues": len(outliers) > 0,
    }

  def detect_invalid_formats(
    self, data: pd.DataFrame, column: str, expected_type: type
  ) -> dict[str, Any]:
    """Detect invalid data formats.

    Args:
        data: Input DataFrame
        column: Column to validate
        expected_type: Expected data type

    Returns:
        Dictionary with format validation results
    """
    if column not in data.columns:
      return {"error": "Column not found"}

    values = data[column].dropna()
    invalid_count = 0
    invalid_indices = []

    for idx, value in values.items():
      if not isinstance(value, expected_type):
        invalid_count += 1
        if len(invalid_indices) < 10:
          invalid_indices.append(idx)

    return {
      "column": column,
      "expected_type": expected_type.__name__,
      "invalid_count": invalid_count,
      "invalid_percentage": round(invalid_count / len(values) * 100, 2),
      "invalid_indices": invalid_indices,
      "has_issues": invalid_count > 0,
    }

  def run_all_checks(self, data: pd.DataFrame) -> dict[str, Any]:
    """Run all anomaly checks on dataset.

    Args:
        data: Input DataFrame

    Returns:
        Comprehensive anomaly report
    """
    report = {
      "missing_values": self.detect_missing_values(data),
      "outliers": {},
      "total_anomalies": 0,
    }

    numeric_cols = data.select_dtypes(include=[np.number]).columns

    for col in numeric_cols:
      outlier_result = self.detect_outliers(data, col)
      if outlier_result.get("has_issues"):
        report["outliers"][col] = outlier_result
        report["total_anomalies"] += outlier_result["outlier_count"]

    if report["missing_values"]["has_issues"]:
      report["total_anomalies"] += len(report["missing_values"]["problematic_columns"])

    report["has_anomalies"] = report["total_anomalies"] > 0

    return report
