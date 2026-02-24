"""Tests for GreatExpectationsValidator."""

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from ml_core.anomaly.ge_validator import GreatExpectationsValidator


@pytest.fixture
def sample_data() -> pd.DataFrame:
  """Sample DataFrame for testing."""
  return pd.DataFrame(
    {
      "id": ["ticket-1", "ticket-2", "ticket-3"],
      "repo": ["hashicorp/terraform", "ansible/ansible", "prometheus/prometheus"],
      "title": ["Bug fix", "Feature request", "Crash report"],
      "state": ["closed", "open", "closed"],
      "completion_hours_business": [10.5, None, 5.2],
    }
  )


@pytest.fixture
def validator() -> GreatExpectationsValidator:
  """Create a fresh validator instance."""
  return GreatExpectationsValidator()


def test_create_expectations(
  validator: GreatExpectationsValidator, sample_data: pd.DataFrame
) -> None:
  """Test that expectations are created for each column."""
  validator.create_expectations(sample_data)
  expectation_types = [e.__class__.__name__ for e in validator.suite.expectations]
  assert "ExpectColumnToExist" in expectation_types


def test_create_expectations_null_check(
  validator: GreatExpectationsValidator,
) -> None:
  """Test that null check expectation is added for columns with low null rate."""
  data = pd.DataFrame({"clean_col": ["a", "b", "c"], "dirty_col": ["a", None, None]})
  validator.create_expectations(data)
  expectation_types = [e.__class__.__name__ for e in validator.suite.expectations]
  assert "ExpectColumnValuesToNotBeNull" in expectation_types


def test_validate_data_success(
  validator: GreatExpectationsValidator, sample_data: pd.DataFrame
) -> None:
  """Test that validation runs and returns expected keys."""
  validator.create_expectations(sample_data)
  result = validator.validate_data(sample_data)
  assert "success" in result
  assert "total_expectations" in result
  assert "failed_expectations" in result
  assert result["total_expectations"] > 0


def test_validate_data_failed_expectations(
  validator: GreatExpectationsValidator,
) -> None:
  """Test that failed expectations are counted correctly."""
  train_data = pd.DataFrame({"col1": ["a", "b", "c"]})
  validator.create_expectations(train_data)

  # Pass data with nulls in a column that was expected to be non-null
  test_data = pd.DataFrame({"col1": ["a", None, "c"]})
  result = validator.validate_data(test_data)
  assert result["failed_expectations"] > 0


def test_save_schema(
  validator: GreatExpectationsValidator, sample_data: pd.DataFrame
) -> None:
  """Test that schema is saved to file correctly."""
  validator.create_expectations(sample_data)

  with tempfile.TemporaryDirectory() as tmpdir:
    output_path = str(Path(tmpdir) / "schema.json")
    validator.save_schema(output_path)

    assert Path(output_path).exists()

    with open(output_path) as f:
      saved = json.load(f)

    assert "expectations" in saved or "expectation_suite_name" in saved
