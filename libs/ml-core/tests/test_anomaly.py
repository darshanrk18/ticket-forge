"""Tests for anomaly detection."""

import pandas as pd
import pytest
from ml_core.anomaly import AnomalyDetector, SchemaValidator


class TestAnomalyDetector:
  """Test cases for AnomalyDetector."""

  @pytest.fixture
  def detector(self) -> AnomalyDetector:
    """Create anomaly detector."""
    return AnomalyDetector(outlier_threshold=3.0)

  def test_detect_missing_values(self, detector: AnomalyDetector) -> None:
    """Test missing value detection."""
    data = pd.DataFrame({"col1": [1, 2, None, 4], "col2": [5, None, None, 8]})

    result = detector.detect_missing_values(data)

    assert result["total_rows"] == 4
    assert "col1" in result["columns_with_missing"]
    assert "col2" in result["columns_with_missing"]

  def test_detect_outliers(self) -> None:
    """Test outlier detection."""
    detector = AnomalyDetector(outlier_threshold=2.0)
    # Use very extreme outlier: 10,000 vs values around 10-14
    data = pd.DataFrame({"values": [10, 12, 11, 13, 10000, 14]})

    result = detector.detect_outliers(data, "values")

    assert result["has_issues"] is True
    assert result["outlier_count"] >= 1

  def test_no_outliers(self, detector: AnomalyDetector) -> None:
    """Test when no outliers present."""
    data = pd.DataFrame({"values": [10, 12, 11, 13, 14, 15]})

    result = detector.detect_outliers(data, "values")

    assert result["outlier_count"] == 0

  def test_run_all_checks(self, detector: AnomalyDetector) -> None:
    """Test running all anomaly checks."""
    data = pd.DataFrame(
      {
        "col1": [1, 2, None, 4],
        "col2": [10, 20, 1000, 30],
      }
    )

    report = detector.run_all_checks(data)

    assert "missing_values" in report
    assert "outliers" in report
    assert "has_anomalies" in report


class TestSchemaValidator:
  """Test cases for SchemaValidator."""

  def test_validate_schema_valid(self) -> None:
    """Test schema validation with valid data."""
    schema = {"name": str, "age": int, "score": float}
    validator = SchemaValidator(schema)

    data = pd.DataFrame(
      {"name": ["alice", "bob"], "age": [25, 30], "score": [95.5, 87.3]}
    )

    result = validator.validate_schema(data)

    assert result["is_valid"] is True
    assert len(result["missing_columns"]) == 0

  def test_validate_schema_missing_columns(self) -> None:
    """Test schema validation with missing columns."""
    schema = {"name": str, "age": int, "score": float}
    validator = SchemaValidator(schema)

    data = pd.DataFrame({"name": ["alice", "bob"], "age": [25, 30]})

    result = validator.validate_schema(data)

    assert result["is_valid"] is False
    assert "score" in result["missing_columns"]

  def test_generate_schema(self) -> None:
    """Test automatic schema generation."""
    data = pd.DataFrame(
      {"name": ["alice", "bob"], "age": [25, 30], "score": [95.5, 87.3]}
    )

    validator = SchemaValidator({})
    schema = validator.generate_schema_from_data(data)

    assert schema["name"] is str
    assert schema["age"] is int
    assert schema["score"] is float
