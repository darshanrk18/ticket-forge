"""Test Gmail alert system."""

import os

import pandas as pd
import pytest
from dotenv import load_dotenv
from ml_core.anomaly import AlertSystem, AnomalyDetector

load_dotenv()

GMAIL_ADDRESS = "mlopsgroup29@gmail.com"
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
RECIPIENT = "mlopsgroup29@gmail.com"


@pytest.mark.skipif(not GMAIL_APP_PASSWORD, reason="GMAIL_APP_PASSWORD not set in .env")
def test_send_gmail_alert() -> None:
  """Test Gmail alert with sample anomaly."""
  sample_data = pd.DataFrame(
    {
      "ticket_id": [1, 2, 3, 4, 5],
      "completion_hours": [10, 20, 1000, 15, 25],
      "assignee": ["alice", None, "bob", "charlie", "alice"],
    }
  )

  detector = AnomalyDetector(outlier_threshold=2.0)
  report = detector.run_all_checks(sample_data)

  assert report["has_anomalies"] is True

  alert_system = AlertSystem()

  if not GMAIL_APP_PASSWORD:
    pytest.skip("GMAIL_APP_PASSWORD not set")

  alert_system.send_gmail_alert(
    report=report,
    recipient=RECIPIENT,
    sender_email=GMAIL_ADDRESS,
    sender_password=GMAIL_APP_PASSWORD,
  )
