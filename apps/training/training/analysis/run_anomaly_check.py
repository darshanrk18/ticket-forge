"""Run complete anomaly detection with alerting."""

import json
import os

import pandas as pd
from dotenv import load_dotenv
from ml_core.anomaly import AlertSystem, AnomalyDetector, SchemaValidator
from shared.configuration import Paths

load_dotenv()

GMAIL_ADDRESS = "mlopsgroup29@gmail.com"
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
RECIPIENT = "mlopsgroup29@gmail.com"


def main() -> None:
  """Run anomaly detection and trigger alerts if needed."""
  print("Starting anomaly detection check...\n")

  data_path = Paths.data_root / "github_issues" / "tickets_transformed_improved.jsonl"

  print("Loading data...")
  tickets = []
  with open(data_path, encoding="utf-8") as f:
    for line in f:
      if line.strip():
        tickets.append(json.loads(line))

  df = pd.DataFrame(tickets)
  print("Loaded", len(df), "tickets\n")

  print("Running anomaly detection...")
  detector = AnomalyDetector(outlier_threshold=3.0)
  anomaly_report = detector.run_all_checks(df)

  print("Anomalies detected:", anomaly_report["has_anomalies"])
  print("Total anomalies:", anomaly_report["total_anomalies"])

  print("\nValidating schema...")
  expected_schema = {
    "id": str,
    "repo": str,
    "title": str,
    "state": str,
    "completion_hours_business": float,
  }

  validator = SchemaValidator(expected_schema)
  schema_result = validator.validate_schema(df)

  print("Schema valid:", schema_result["is_valid"])
  if not schema_result["is_valid"]:
    print("Missing columns:", schema_result["missing_columns"])
    print("Type mismatches:", schema_result["type_mismatches"])

  print("\nGenerating statistics...")
  stats = validator.generate_statistics(df)
  print("Total rows:", stats["row_count"])
  print("Total columns:", stats["column_count"])

  if anomaly_report["has_anomalies"] and GMAIL_APP_PASSWORD:
    print("\nTriggering alert...")
    alert_system = AlertSystem(alert_threshold=1)
    alert_system.send_gmail_alert(
      report=anomaly_report,
      recipient=RECIPIENT,
      sender_email=GMAIL_ADDRESS,
      sender_password=GMAIL_APP_PASSWORD,
    )
    print("Alert sent to", RECIPIENT)
  elif anomaly_report["has_anomalies"]:
    print("\nAnomalies found but GMAIL_APP_PASSWORD not set.")
  else:
    print("\nNo anomalies detected. No alert needed.")

  print("\nAnomaly check complete!")


if __name__ == "__main__":
  main()
