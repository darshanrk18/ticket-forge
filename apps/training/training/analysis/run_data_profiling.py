"""Data profiling script using Great Expectations and custom skew detection."""

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from ml_core.anomaly.ge_validator import GreatExpectationsValidator
from ml_core.anomaly.validator import SchemaValidator
from shared.configuration import Paths

# Suppress noisy GE logs
logging.getLogger("great_expectations").setLevel(logging.ERROR)
logging.getLogger("great_expectations.data_context").setLevel(logging.ERROR)
logging.getLogger("great_expectations.data_context.types.base").setLevel(logging.ERROR)

NUMERIC_COLS = [
  "completion_hours_business",
  "seniority_enum",
  "historical_avg_completion_hours",
]
CATEGORICAL_COLS = ["repo", "issue_type", "state"]


class NumpyEncoder(json.JSONEncoder):
  """Custom JSON encoder to handle numpy types."""

  def default(self, o: object) -> object:
    """Encode numpy types to native Python types."""
    if isinstance(o, np.integer):
      return int(o)
    if isinstance(o, np.floating):
      return float(o)
    if isinstance(o, np.bool_):
      return bool(o)
    if isinstance(o, np.ndarray):
      return o.tolist()
    return super().default(o)


def load_jsonl(path: Path) -> pd.DataFrame:
  """Load a JSONL file into a DataFrame."""
  tickets = []
  with open(path, encoding="utf-8") as f:
    for line in f:
      if line.strip():
        tickets.append(json.loads(line))
  return pd.DataFrame(tickets)


def detect_skew(sample_df: pd.DataFrame, full_df: pd.DataFrame) -> dict:
  """Compare distributions between sample and full dataset.

  Args:
      sample_df: Sampled dataset
      full_df: Full dataset

  Returns:
      Dictionary of skew results per column
  """
  skew_results = {}

  for col in NUMERIC_COLS:
    if col not in sample_df.columns or col not in full_df.columns:
      continue

    sample_mean = float(sample_df[col].dropna().mean())  # type: ignore[arg-type]
    full_mean = float(full_df[col].dropna().mean())  # type: ignore[arg-type]
    sample_std = float(sample_df[col].dropna().std())  # type: ignore[arg-type]
    full_std = float(full_df[col].dropna().std())  # type: ignore[arg-type]

    mean_diff_pct = abs(sample_mean - full_mean) / full_mean * 100 if full_mean else 0
    std_diff_pct = abs(sample_std - full_std) / full_std * 100 if full_std else 0

    skew_results[col] = {
      "sample_mean": round(sample_mean, 4),
      "full_mean": round(full_mean, 4),
      "mean_diff_pct": round(mean_diff_pct, 2),
      "sample_std": round(sample_std, 4),
      "full_std": round(full_std, 4),
      "std_diff_pct": round(std_diff_pct, 2),
      "skewed": mean_diff_pct > 10,
    }

  for col in CATEGORICAL_COLS:
    if col not in sample_df.columns or col not in full_df.columns:
      continue

    sample_dist = sample_df[col].value_counts(normalize=True).to_dict()
    full_dist = full_df[col].value_counts(normalize=True).to_dict()

    max_diff = 0.0
    for key in full_dist:
      sample_val = sample_dist.get(key, 0.0)
      diff = abs(sample_val - full_dist[key])
      max_diff = max(max_diff, diff)

    skew_results[col] = {
      "sample_distribution": {k: round(v, 4) for k, v in sample_dist.items()},
      "full_distribution": {k: round(v, 4) for k, v in full_dist.items()},
      "max_distribution_diff": round(max_diff, 4),
      "skewed": max_diff > 0.1,
    }

  return skew_results


def run_data_profiling(
  data_path: str | Path,
  reference_path: str | Path | None = None,
  output_dir: str | Path | None = None,
) -> dict[str, Any]:
  """Run data profiling on transformed tickets.

  Args:
      data_path: Path to transformed tickets JSONL file.
      reference_path: Optional path to full dataset for skew detection.
      output_dir: Optional directory to save profile outputs.

  Returns:
      Dictionary with profiling results including GE validation and skew.
  """
  data_path = Path(data_path)
  output_dir = Path(output_dir) if output_dir else data_path.parent

  print("Loading dataset...")
  df = load_jsonl(data_path)
  print("Loaded", len(df), "tickets")

  # Load reference dataset for skew detection
  full_df = None
  if reference_path and Path(reference_path).exists():
    print("Loading reference dataset for skew detection...")
    full_df = load_jsonl(Path(reference_path))
    print("Loaded", len(full_df), "reference tickets")

  # 1. Schema statistics
  print("\nGenerating statistics...")
  validator = SchemaValidator({})
  stats = validator.generate_statistics(df)
  schema = validator.generate_schema_from_data(df)
  print("Rows:", stats["row_count"])
  print("Columns:", stats["column_count"])

  # 2. Great Expectations validation
  print("\nRunning Great Expectations validation...")
  ge_validator = GreatExpectationsValidator()
  ge_validator.create_expectations(df)
  validation_results = ge_validator.validate_data(df)
  print("Validation passed:", validation_results["success"])
  print("Total expectations:", validation_results["total_expectations"])
  print("Failed expectations:", validation_results["failed_expectations"])

  # 3. Save GE schema
  schema_output = output_dir / "ticket_schema.json"
  ge_validator.save_schema(str(schema_output))

  # 4. Skew detection
  skew_results = {}
  if full_df is not None:
    print("\nDetecting skew between datasets...")
    skew_results = detect_skew(df, full_df)
    skewed_cols = [col for col, res in skew_results.items() if res["skewed"]]
    if skewed_cols:
      print("Skewed columns:", skewed_cols)
    else:
      print("No significant skew detected")

  # 5. Save full profile report
  profile = {
    "dataset": str(data_path),
    "row_count": stats["row_count"],
    "column_count": stats["column_count"],
    "schema": {col: t.__name__ for col, t in schema.items()},
    "numeric_stats": stats["numeric_stats"],
    "categorical_stats": stats["categorical_stats"],
    "ge_validation": validation_results,
    "skew_vs_reference": skew_results,
  }

  profile_output = output_dir / "data_profile_report.json"
  with open(profile_output, "w", encoding="utf-8") as f:
    json.dump(profile, f, indent=2, cls=NumpyEncoder)

  print("\nProfile report saved to", profile_output)
  print("Done!")

  return profile


def main() -> None:
  """Run data profiling from command line."""
  parser = argparse.ArgumentParser(
    description="Run data profiling on transformed ticket data."
  )
  parser.add_argument(
    "--data-path",
    type=str,
    default=str(Paths.data_root / "github_issues" / "sample_tickets_transformed.jsonl"),
    help="Path to transformed tickets JSONL file.",
  )
  parser.add_argument(
    "--reference-path",
    type=str,
    default=str(
      Paths.data_root / "github_issues" / "tickets_transformed_improved.jsonl"
    ),
    help="Path to full dataset for skew detection.",
  )
  args = parser.parse_args()

  run_data_profiling(
    data_path=args.data_path,
    reference_path=args.reference_path,
  )


if __name__ == "__main__":
  main()
