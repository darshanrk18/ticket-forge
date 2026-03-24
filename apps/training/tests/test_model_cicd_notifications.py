"""Tests for notification event recording in gate reports."""

from __future__ import annotations

import json
from pathlib import Path

from training.analysis.gate_report import NotificationEvent, append_notification_event


def test_append_notification_event_updates_report(tmp_path: Path) -> None:
  """Notification append API writes event entries to gate report."""
  report_path = tmp_path / "gate_report.json"
  report_path.write_text(
    json.dumps(
      {
        "run_id": "run-1",
        "candidate_model": "forest",
        "validation_gate": {"passed": True, "metrics": {}, "thresholds": {}},
        "bias_gate": {"passed": True, "slices_evaluated": []},
        "regression_guardrail": {
          "passed": True,
          "max_allowed_degradation": 0.1,
          "metric_deltas": {},
        },
        "promotion_decision": {"decision": "promoted", "promoted": True},
        "generated_at": "2026-03-23T00:00:00+00:00",
      }
    ),
    encoding="utf-8",
  )

  append_notification_event(
    report_path,
    NotificationEvent(
      event_type="completed",
      channel="email",
      recipient="mlopsgroup29@gmail.com",
      delivery_status="sent",
    ),
  )

  updated = json.loads(report_path.read_text(encoding="utf-8"))
  assert len(updated["notification_events"]) == 1
  assert updated["notification_events"][0]["event_type"] == "completed"
