"""Schema validation for data quality."""

from typing import Any

import numpy as np
import pandas as pd


class SchemaValidator:
  """Validate data against expected schema."""

  def __init__(self, expected_schema: dict[str, type]) -> None:
    """Initialize schema validator.

    Args:
        expected_schema: Dict mapping column names to expected types
    """
    self.expected_schema = expected_schema

  def validate_schema(self, data: pd.DataFrame) -> dict[str, Any]:
    """Validate DataFrame against expected schema.

    Args:
        data: Input DataFrame to validate

    Returns:
        Validation results
    """
    missing_columns = []
    extra_columns = []
    type_mismatches = []

    expected_cols = set(self.expected_schema.keys())
    actual_cols = set(data.columns)

    missing_columns = list(expected_cols - actual_cols)
    extra_columns = list(actual_cols - expected_cols)

    for col in expected_cols.intersection(actual_cols):
      expected_type = self.expected_schema[col]
      actual_dtype = data[col].dtype

      if not self._is_compatible_type(actual_dtype, expected_type):
        type_mismatches.append(
          {
            "column": col,
            "expected": expected_type.__name__,
            "actual": str(actual_dtype),
          }
        )

    return {
      "missing_columns": missing_columns,
      "extra_columns": extra_columns,
      "type_mismatches": type_mismatches,
      "is_valid": (
        len(missing_columns) == 0
        and len(extra_columns) == 0
        and len(type_mismatches) == 0
      ),
    }

  def _is_compatible_type(self, actual_dtype: object, expected_type: type) -> bool:
    """Check if actual dtype is compatible with expected type."""
    if expected_type is str:
      return actual_dtype is object or pd.api.types.is_string_dtype(actual_dtype)
    if expected_type is int:
      return pd.api.types.is_integer_dtype(actual_dtype)
    if expected_type is float:
      return pd.api.types.is_float_dtype(actual_dtype)
    return False

  def generate_schema_from_data(self, data: pd.DataFrame) -> dict[str, type]:
    """Generate schema from existing data.

    Args:
        data: Input DataFrame

    Returns:
        Generated schema
    """
    schema = {}

    for col in data.columns:
      dtype = data[col].dtype

      if pd.api.types.is_integer_dtype(dtype):
        schema[col] = int
      elif pd.api.types.is_float_dtype(dtype):
        schema[col] = float
      elif pd.api.types.is_string_dtype(dtype) or dtype is object:
        schema[col] = str
      else:
        schema[col] = object

    return schema

  def generate_statistics(self, data: pd.DataFrame) -> dict[str, Any]:
    """Generate descriptive statistics for dataset.

    Args:
        data: Input DataFrame

    Returns:
        Statistical summary
    """
    stats = {
      "row_count": len(data),
      "column_count": len(data.columns),
      "columns": list(data.columns),
      "numeric_stats": {},
      "categorical_stats": {},
    }

    numeric_cols = data.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
      col_data = data[col].dropna()
      if len(col_data) > 0:
        stats["numeric_stats"][col] = {
          "mean": round(col_data.mean(), 2),
          "std": round(col_data.std(), 2),
          "min": round(col_data.min(), 2),
          "max": round(col_data.max(), 2),
          "missing": int(data[col].isnull().sum()),  # type: ignore[arg-type,call-overload]
        }

    categorical_cols = data.select_dtypes(include=[object]).columns
    for col in categorical_cols:
      if isinstance(data[col].iloc[0], list):
        continue
      unique_count = data[col].nunique()
      if unique_count < 100:
        stats["categorical_stats"][col] = {
          "unique_values": unique_count,
          "top_values": data[col].value_counts().head(5).to_dict(),
          "missing": int(data[col].isnull().sum()),  # type: ignore[arg-type,call-overload]
        }

    return stats
