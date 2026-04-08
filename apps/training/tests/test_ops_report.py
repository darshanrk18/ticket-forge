"""Tests for unified operations reporting helpers."""

from __future__ import annotations

from training.analysis.ops_report import (
  build_ops_report,
  render_ops_body,
  render_ops_subject,
)


def test_build_ops_report_keeps_shared_fields() -> None:
  """Operations report stores shared workflow metadata."""
  report = build_ops_report(
    report_type="deployment",
    workflow_name="Airflow Deploy",
    status="success",
    trigger="workflow_run",
    workflow_url="https://example.com/run/1",
    commit_sha="abc123",
    source_ref="main",
    deployment_target="airflow-vm-prod",
    deployment_revision="def456",
  )

  assert report["report_type"] == "deployment"
  assert report["workflow_name"] == "Airflow Deploy"
  assert report["deployment_revision"] == "def456"
  assert report["failure_reasons"] == []


def test_render_ops_body_includes_failure_reasons_and_metadata() -> None:
  """Rendered body includes the most useful triage fields."""
  report = build_ops_report(
    report_type="retraining",
    workflow_name="Model CI/CD",
    status="failure",
    trigger="workflow_dispatch",
    workflow_url="https://example.com/run/2",
    trigger_reason="drift:monitor-1",
    dataset_version="2026-04-06T10:00:00Z",
    model_version="7",
    failure_reasons=["promotion-failed", "regression-threshold-exceeded"],
    metadata={
      "drift_report_uri": "gs://bucket/monitoring/reports/run/drift_report.json"
    },
  )

  body = render_ops_body(report)

  assert "Trigger Reason: drift:monitor-1" in body
  assert "Model Version: 7" in body
  assert "promotion-failed" in body
  assert "drift_report_uri" in body
  assert render_ops_subject(report) == "[TicketForge] Retraining FAILURE"
