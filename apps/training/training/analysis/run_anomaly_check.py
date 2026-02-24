"""Run complete anomaly detection with alerting."""

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from ml_core.anomaly import AlertSystem, AnomalyDetector, SchemaValidator
from shared.configuration import Paths, getenv

GMAIL_ADDRESS = getenv("GMAIL_APP_USERNAME")
GMAIL_APP_PASSWORD = getenv("GMAIL_APP_PASSWORD")


def run_anomaly_check(  # noqa: PLR0915
  data_path: str | Path,
  *,
  outlier_threshold: float = 3.0,
  enable_alerts: bool = True,
) -> dict[str, Any]:
  """Run anomaly detection and optionally trigger alerts.

  Args:
      data_path: Path to transformed tickets JSONL file.
      outlier_threshold: Z-score threshold for outlier detection.
      enable_alerts: Whether to send alert emails on anomalies.

  Returns:
      Results including anomaly report, schema validation, and summary text.
  """
  print("Starting anomaly detection check...\n")

  data_path = Path(data_path)

  print("Loading data...")
  tickets = []
  with open(data_path, encoding="utf-8") as f:
    for line in f:
      if line.strip():
        tickets.append(json.loads(line))

  df = pd.DataFrame(tickets)
  print("Loaded", len(df), "tickets\n")

  print("Running anomaly detection...")
  detector = AnomalyDetector(outlier_threshold=outlier_threshold)
  anomaly_report = detector.run_all_checks(df)

  lines: list[str] = []
  lines.append("=" * 80)
  lines.append("ANOMALY DETECTION RESULTS")
  lines.append("=" * 80)
  lines.append(f"Anomalies report: {anomaly_report}")
  lines.append(f"Anomalies detected: {anomaly_report['has_anomalies']}")
  lines.append(f"Total anomalies: {anomaly_report['total_anomalies']}")

  lines.append(f"Anomalies report: {anomaly_report}")
  print("Anomalies detected:", anomaly_report["has_anomalies"])
  print("Total anomalies:", anomaly_report["total_anomalies"])

  print("\nValidating schema...")
  expected_schema = {
    "id": str,
    "repo": str,
    "title": str,
    "body": str,
    "url": str,
    "state": str,
    "issue_type": str,
    "labels": str,
    "assignee": str,
    "seniority": str,
    "seniority_enum": int,
    "historical_avg_completion_hours": float,
    "completion_hours_business": float,
    "normalized_text": str,
    "keywords": object,
    "embedding": object,
    "embedding_model": str,
    "created_at": str,
    "assigned_at": str,
    "closed_at": str,
    "comments_count": int,
  }

  validator = SchemaValidator(expected_schema)
  schema_result = validator.validate_schema(df)

  print("Schema valid:", schema_result["is_valid"])
  if not schema_result["is_valid"]:
    lines.append("")
    lines.append("SCHEMA VALIDATION ISSUES:")
    print("Missing columns:", schema_result["missing_columns"])
    print("Type mismatches:", schema_result["type_mismatches"])
    print("Extra columns:", schema_result["extra_columns"])
    lines.append(f"  Missing columns: {schema_result['missing_columns']}")
    lines.append(f"  Type mismatches: {schema_result['type_mismatches']}")
    lines.append(f"  Extra columns: {schema_result['extra_columns']}")

  print("\nGenerating statistics...")
  stats = validator.generate_statistics(df)
  print("Total rows:", stats["row_count"])
  print("Total columns:", stats["column_count"])

  if enable_alerts and anomaly_report["has_anomalies"] and GMAIL_APP_PASSWORD:
    print("\nTriggering alert...")
    alert_system = AlertSystem(alert_threshold=1)
    alert_system.send_gmail_alert(
      report=anomaly_report,
      recipient=GMAIL_ADDRESS,
      sender_email=GMAIL_ADDRESS,
      sender_password=GMAIL_APP_PASSWORD,
    )
    print("Alert sent to", GMAIL_ADDRESS)
  elif enable_alerts and anomaly_report["has_anomalies"]:
    print("\nAnomalies found but GMAIL_APP_PASSWORD not set.")
  else:
    print("\nNo anomalies detected. No alert needed.")

  print("\nAnomaly check complete!")

  return {
    "anomaly_report": anomaly_report,
    "schema_result": schema_result,
    "statistics": stats,
    "text_report": "\n".join(lines),
  }


def main() -> None:
  """Run anomaly detection and trigger alerts if needed."""
  parser = argparse.ArgumentParser(
    description="Run anomaly detection on transformed ticket data."
  )
  parser.add_argument(
    "--data-path",
    type=str,
    default=str(
      Paths.data_root / "github_issues" / "tickets_transformed_improved.jsonl"
    ),
    help="Path to transformed tickets JSONL file.",
  )
  parser.add_argument(
    "--outlier-threshold",
    type=float,
    default=3.0,
    help="Z-score threshold for outlier detection.",
  )
  parser.add_argument(
    "--disable-alerts",
    action="store_true",
    help="Disable alert emails when anomalies are detected.",
  )
  args = parser.parse_args()

  run_anomaly_check(
    data_path=args.data_path,
    outlier_threshold=args.outlier_threshold,
    enable_alerts=not args.disable_alerts,
  )


if __name__ == "__main__":
  main()
