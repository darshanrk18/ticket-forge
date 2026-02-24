"""Alert system for data quality issues."""

import logging
from datetime import datetime
from typing import Any


class AlertSystem:
  """Send alerts for data quality issues."""

  def __init__(self, alert_threshold: int = 1) -> None:
    """Initialize alert system.

    Args:
        alert_threshold: Minimum number of issues to trigger alert
    """
    self.alert_threshold = alert_threshold
    self.logger = logging.getLogger(__name__)

  def check_and_alert(self, anomaly_report: dict[str, Any]) -> None:
    """Check anomaly report and send alerts if needed.

    Args:
        anomaly_report: Report from AnomalyDetector
    """
    if not anomaly_report.get("has_anomalies", False):
      self.logger.info("No anomalies detected. Data quality OK.")
      return

    total_anomalies = anomaly_report.get("total_anomalies", 0)

    if total_anomalies >= self.alert_threshold:
      self._send_alert(anomaly_report)

  def _send_alert(self, report: dict[str, Any]) -> None:
    """Send alert about data quality issues.

    Args:
        report: Anomaly report
    """
    alert_message = self._format_alert_message(report)

    self.logger.warning("DATA QUALITY ALERT")
    self.logger.warning(alert_message)

    print("\n" + "=" * 80)
    print("ALERT: DATA QUALITY ISSUES DETECTED")
    print("=" * 80)
    print(alert_message)
    print("=" * 80 + "\n")

  def _format_alert_message(self, report: dict[str, Any]) -> str:
    """Format alert message from report."""
    lines = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("Timestamp: " + timestamp)
    lines.append("Total anomalies: " + str(report.get("total_anomalies", 0)))

    if report.get("missing_values", {}).get("has_issues"):
      missing = report["missing_values"]["problematic_columns"]
      lines.append("\nMissing values detected in columns:")
      for col, pct in missing.items():
        lines.append("  - " + col + ": " + str(pct) + "%")

    if report.get("outliers"):
      lines.append("\nOutliers detected in columns:")
      for col, info in report["outliers"].items():
        count = info["outlier_count"]
        pct = info["outlier_percentage"]
        msg = "  - " + col + ": " + str(count) + " outliers"
        lines.append(msg + " (" + str(pct) + "%)")

    lines.append("\nAction required: Review data quality before training.")

    return "\n".join(lines)

  def send_email_alert(self, report: dict[str, Any], recipient: str) -> None:
    """Send email alert (placeholder for future implementation).

    Args:
        report: Anomaly report
        recipient: Email recipient
    """
    message = self._format_alert_message(report)
    self.logger.info("Email alert would be sent to: " + recipient)
    self.logger.info("Message: " + message)

  def send_gmail_alert(
    self,
    report: dict[str, Any],
    recipient: str,
    sender_email: str,
    sender_password: str,
  ) -> None:
    """Send Gmail alert.

    Args:
        report: Anomaly report
        recipient: Recipient email
        sender_email: Gmail address
        sender_password: Gmail app password
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    message = self._format_alert_message(report)

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient
    msg["Subject"] = "DATA QUALITY ALERT - Anomalies Detected"

    msg.attach(MIMEText(message, "plain"))

    try:
      server = smtplib.SMTP("smtp.gmail.com", 587)
      server.starttls()
      server.login(sender_email, sender_password)
      server.send_message(msg)
      server.quit()

      self.logger.info("Email alert sent successfully to: " + recipient)
    except Exception:
      self.logger.exception("Failed to send email")
