"""Unified operations reporting helpers for deploy and retrain workflows."""

from __future__ import annotations

import json
import smtplib
from datetime import UTC, datetime
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any


def build_ops_report(  # noqa: PLR0913
  *,
  report_type: str,
  workflow_name: str,
  status: str,
  trigger: str,
  workflow_url: str,
  commit_sha: str | None = None,
  source_ref: str | None = None,
  trigger_reason: str | None = None,
  dataset_source: str | None = None,
  dataset_version: str | None = None,
  dataset_uri: str | None = None,
  model_version: str | None = None,
  deployment_target: str | None = None,
  deployment_revision: str | None = None,
  failure_reasons: list[str] | None = None,
  metadata: dict[str, object] | None = None,
) -> dict[str, Any]:
  """Build a machine-readable report shared by operations workflows."""
  return {
    "report_type": report_type,
    "workflow_name": workflow_name,
    "status": status.lower(),
    "trigger": trigger,
    "trigger_reason": trigger_reason,
    "workflow_url": workflow_url,
    "commit_sha": commit_sha,
    "source_ref": source_ref,
    "dataset_source": dataset_source,
    "dataset_version": dataset_version,
    "dataset_uri": dataset_uri,
    "model_version": model_version,
    "deployment_target": deployment_target,
    "deployment_revision": deployment_revision,
    "failure_reasons": failure_reasons or [],
    "metadata": metadata or {},
    "generated_at": datetime.now(tz=UTC).isoformat(),
  }


def write_ops_report(path: str | Path, report: dict[str, Any]) -> Path:
  """Persist an operations report to disk."""
  report_path = Path(path)
  report_path.parent.mkdir(parents=True, exist_ok=True)
  with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
  return report_path


def render_ops_subject(report: dict[str, Any]) -> str:
  """Build a concise email subject for an operations report."""
  report_type = str(report.get("report_type", "operations")).replace("_", " ").title()
  status = str(report.get("status", "unknown")).upper()
  return f"[TicketForge] {report_type} {status}"


def render_ops_body(report: dict[str, Any]) -> str:
  """Render a readable plain-text email body from an operations report."""
  lines = [
    f"Workflow: {report.get('workflow_name', 'unknown')}",
    f"Type: {report.get('report_type', 'operations')}",
    f"Status: {str(report.get('status', 'unknown')).upper()}",
    f"Trigger: {report.get('trigger', 'unknown')}",
    f"Run: {report.get('workflow_url', '')}",
  ]

  optional_fields = [
    ("Trigger Reason", report.get("trigger_reason")),
    ("Commit SHA", report.get("commit_sha")),
    ("Source Ref", report.get("source_ref")),
    ("Dataset Source", report.get("dataset_source")),
    ("Dataset Version", report.get("dataset_version")),
    ("Dataset URI", report.get("dataset_uri")),
    ("Model Version", report.get("model_version")),
    ("Deployment Target", report.get("deployment_target")),
    ("Deployment Revision", report.get("deployment_revision")),
  ]
  for label, value in optional_fields:
    if value:
      lines.append(f"{label}: {value}")

  failure_reasons = report.get("failure_reasons", [])
  if isinstance(failure_reasons, list) and failure_reasons:
    lines.extend(["", "Failure Reasons:"])
    for reason in failure_reasons:
      lines.append(f"- {reason}")

  metadata = report.get("metadata", {})
  if isinstance(metadata, dict) and metadata:
    lines.extend(["", "Additional Metadata:"])
    for key in sorted(metadata):
      lines.append(f"- {key}: {metadata[key]}")

  return "\n".join(lines) + "\n"


def send_gmail_notification(
  report: dict[str, Any],
  *,
  sender_email: str,
  sender_password: str,
  recipient: str | None = None,
) -> None:
  """Send an operations report through Gmail SMTP."""
  target = recipient or sender_email
  body = render_ops_body(report)
  msg = MIMEText(f"<pre>{body}</pre>", "html")
  msg["Subject"] = render_ops_subject(report)
  msg["From"] = sender_email
  msg["To"] = target

  with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
    smtp.login(sender_email, sender_password)
    smtp.sendmail(sender_email, [target], msg.as_string())
