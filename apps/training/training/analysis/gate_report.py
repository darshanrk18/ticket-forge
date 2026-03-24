"""Gate decision report helpers for model CI/CD runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from shared.configuration import Paths
from shared.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class NotificationEvent:
  """Represents a notification event linked to a gate decision report.

  Attributes:
      event_type: Event type like completed/failed/promotion_blocked.
      channel: Delivery channel, for example email or slack.
      recipient: Target recipient identifier.
      delivery_status: sent, failed, pending, or skipped.
  """

  event_type: str
  channel: str
  recipient: str
  delivery_status: str


def _to_builtin(value: object) -> object:
  """Convert nested structures into JSON-safe Python builtins."""
  if isinstance(value, dict):
    return {str(k): _to_builtin(v) for k, v in value.items()}
  if isinstance(value, list | tuple | set):
    return [_to_builtin(v) for v in value]
  if isinstance(value, Path):
    return str(value)
  if isinstance(value, datetime):
    return value.astimezone(UTC).isoformat()
  if isinstance(value, str | int | float | bool) or value is None:
    return value
  return value


def build_gate_report(
  run_id: str,
  candidate_model: str,
  gate_sections: dict[str, object],
  promotion_decision: dict[str, object],
  baseline_model_version: str | None = None,
) -> dict[str, object]:
  """Build a gate report that conforms to the contract schema.

  Args:
      run_id: CI run identifier.
      candidate_model: Best candidate model name.
      gate_sections: Validation, bias, and regression gate sections.
      promotion_decision: Promotion decision dictionary.
      baseline_model_version: Optional baseline production version.

  Returns:
      Gate report as a JSON-serializable dictionary.
  """
  report = {
    "run_id": run_id,
    "candidate_model": candidate_model,
    "baseline_model_version": baseline_model_version,
    "validation_gate": gate_sections["validation_gate"],
    "bias_gate": gate_sections["bias_gate"],
    "regression_guardrail": gate_sections["regression_guardrail"],
    "promotion_decision": promotion_decision,
    "notification_events": [],
    "generated_at": datetime.now(tz=UTC).isoformat(),
  }
  converted = _to_builtin(report)
  if not isinstance(converted, dict):
    msg = "Gate report serialization produced an invalid top-level payload"
    raise TypeError(msg)
  return converted


def write_gate_report(run_id: str, report: dict[str, object]) -> Path:
  """Write the gate report to the run directory.

  Args:
      run_id: Training run identifier.
      report: Report dictionary.

  Returns:
      Path to the written gate report.
  """
  run_dir = Paths.models_root / run_id
  run_dir.mkdir(parents=True, exist_ok=True)

  report_path = run_dir / "gate_report.json"
  with open(report_path, "w", encoding="utf-8") as f:
    json.dump(_to_builtin(report), f, indent=2)

  logger.info("Gate report written to %s", report_path)
  return report_path


def append_notification_event(
  report_path: Path,
  event: NotificationEvent,
) -> dict[str, object]:
  """Append a notification event to an existing gate report.

  Args:
      report_path: Path to an existing gate report JSON file.
      event: Notification event to append.

  Returns:
      Updated report dictionary.
  """
  with open(report_path, encoding="utf-8") as f:
    report = json.load(f)

  events = report.get("notification_events", [])
  events.append(
    {
      "event_type": event.event_type,
      "channel": event.channel,
      "recipient": event.recipient,
      "delivery_status": event.delivery_status,
      "sent_at": datetime.now(tz=UTC).isoformat(),
    }
  )
  report["notification_events"] = events

  with open(report_path, "w", encoding="utf-8") as f:
    json.dump(_to_builtin(report), f, indent=2)

  logger.info("Updated notification events in %s", report_path)
  return report
