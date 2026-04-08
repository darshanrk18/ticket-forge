"""Run drift monitoring against the latest cloud-published training dataset."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from google.cloud import storage
from shared.configuration import Paths, getenv_or
from shared.logging import get_logger
from training.analysis.drift_detection import (
  DriftThresholds,
  compare_profile_reports,
  load_drift_thresholds,
  write_drift_report,
)
from training.analysis.run_data_profiling import run_data_profiling
from training.cloud_storage_loader import (
  find_downloaded_dataset_file,
  resolve_cloud_dataset,
)

logger = get_logger(__name__)

_DEFAULT_BASELINE_OBJECT = "monitoring/latest_data_profile_report.json"
_DEFAULT_LATEST_REPORT_OBJECT = "monitoring/latest_drift_report.json"
_DEFAULT_REPORTS_PREFIX = "monitoring/reports"
_DEFAULT_SERVING_BASELINE_OBJECT = "monitoring/serving/latest_profile_report.json"
_DEFAULT_SERVING_LATEST_REPORT_OBJECT = "monitoring/serving/latest_drift_report.json"
_DEFAULT_SERVING_REPORTS_PREFIX = "monitoring/serving/reports"
_SERVING_NUMERIC_COLS = [
  "latency_ms",
  "confidence",
  "comments_count",
  "historical_avg_completion_hours",
  "keyword_count",
  "title_length",
  "body_length",
  "time_to_assignment_hours",
]
_SERVING_CATEGORICAL_COLS = [
  "repo",
  "issue_type",
  "predicted_bucket",
  "model_version",
  "rail",
]


@dataclass(frozen=True)
class MonitoringContext:
  """Resolved monitoring inputs for a single run."""

  current_profile: dict[str, Any]
  bucket_name: str
  baseline_object: str
  latest_report_object: str
  reports_prefix: str
  baseline_profile: dict[str, Any] | None
  dataset_id: str
  dataset_uri: str
  dataset_version: str


def _parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Run dataset drift monitoring.")
  parser.add_argument("--runid", required=True, help="Monitoring run identifier")
  parser.add_argument("--bucket-uri", default=None, help="gs:// bucket URI override")
  parser.add_argument(
    "--monitor-source",
    default="serving",
    choices=["serving", "gcs"],
    help="Data source to profile for drift detection",
  )
  parser.add_argument(
    "--backend-url",
    default=None,
    help="Explicit backend URL for serving-event export",
  )
  parser.add_argument("--trigger", default="schedule", help="Trigger source")
  parser.add_argument(
    "--trigger-reason",
    default="scheduled-monitoring",
    help="Human-readable reason for this monitoring run",
  )
  parser.add_argument(
    "--serving-export-limit",
    type=int,
    default=2000,
    help="Maximum number of recent serving events to export for monitoring",
  )
  parser.add_argument(
    "--baseline-object",
    default=_DEFAULT_BASELINE_OBJECT,
    help="Bucket object path for the latest baseline profile JSON",
  )
  parser.add_argument(
    "--reports-prefix",
    default=_DEFAULT_REPORTS_PREFIX,
    help="Bucket prefix under which drift reports are persisted",
  )
  return parser.parse_args()


def _read_json_blob(bucket_name: str, object_name: str) -> dict[str, Any] | None:
  """Read a JSON object from Cloud Storage when it exists."""
  client = storage.Client()
  bucket = client.bucket(bucket_name)
  blob = bucket.blob(object_name)
  if not blob.exists(client):
    return None

  raw = blob.download_as_text()
  parsed = json.loads(raw)
  if not isinstance(parsed, dict):
    msg = f"Expected JSON object in gs://{bucket_name}/{object_name}"
    raise TypeError(msg)
  return parsed


def _write_json_blob(
  bucket_name: str,
  object_name: str,
  payload: dict[str, Any],
) -> str:
  """Write a JSON object to Cloud Storage and return the gs:// URI."""
  client = storage.Client()
  bucket = client.bucket(bucket_name)
  blob = bucket.blob(object_name)
  blob.upload_from_string(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    content_type="application/json",
  )
  return f"gs://{bucket_name}/{object_name}"


def _blob_uri(bucket_name: str, object_name: str) -> str:
  """Return the gs:// URI for a bucket object path."""
  return f"gs://{bucket_name}/{object_name}"


def _resolve_bucket_name(bucket_uri: str | None) -> str:
  """Resolve the monitoring bucket name from args/env."""
  effective_bucket_uri = bucket_uri or getenv_or("GCS_BUCKET_NAME", "")
  if not effective_bucket_uri:
    msg = "GCS_BUCKET_NAME (or --bucket-uri) must be set for monitoring reports"
    raise ValueError(msg)
  if not effective_bucket_uri.startswith("gs://"):
    msg = f"Invalid bucket URI: {effective_bucket_uri}"
    raise ValueError(msg)
  stripped = effective_bucket_uri.removeprefix("gs://")
  return stripped.split("/", 1)[0]


def _resolve_backend_url(backend_url: str | None) -> str:
  """Resolve the production backend URL from args/env/gcloud."""
  if backend_url:
    return backend_url.rstrip("/")

  env_url = getenv_or("TICKETFORGE_BACKEND_URL", "")
  if env_url:
    return env_url.rstrip("/")

  service = getenv_or("TICKETFORGE_BACKEND_SERVICE", "ticketforge-backend")
  region = getenv_or("TICKETFORGE_GCP_REGION", "us-east1")
  project = getenv_or("TICKETFORGE_GCP_PROJECT_ID")
  cmd = [
    "gcloud",
    "run",
    "services",
    "describe",
    service,
    "--region",
    region,
    "--format=value(status.url)",
  ]
  if project:
    cmd.extend(["--project", project])

  result = subprocess.run(cmd, capture_output=True, text=True, check=False)
  if result.returncode != 0 or not result.stdout.strip():
    msg = (
      "Could not resolve backend URL for serving monitoring. "
      f"stderr={result.stderr.strip()}"
    )
    raise RuntimeError(msg)
  return result.stdout.strip().rstrip("/")


def _write_serving_records(path: Path, records: list[dict[str, Any]]) -> int:
  """Persist serving-event export as JSONL for profiling."""
  path.parent.mkdir(parents=True, exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    for record in records:
      f.write(json.dumps(record, sort_keys=True) + "\n")
  return len(records)


def _fetch_serving_records(
  backend_url: str,
  *,
  limit: int,
) -> list[dict[str, Any]]:
  """Fetch recent serving telemetry from the deployed backend."""
  response = httpx.get(
    f"{backend_url}/api/v1/inference/monitoring/export",
    params={"limit": limit},
    timeout=30.0,
  )
  response.raise_for_status()
  payload = response.json()
  if not isinstance(payload, list):
    msg = "Backend monitoring export must return a JSON array"
    raise TypeError(msg)
  return [record for record in payload if isinstance(record, dict)]


def _empty_serving_profile(export_path: Path) -> dict[str, Any]:
  """Build an empty serving profile when no inference events exist yet."""
  return {
    "dataset": str(export_path),
    "row_count": 0,
    "column_count": 0,
    "schema": {},
    "numeric_stats": {},
    "categorical_stats": {},
    "ge_validation": {
      "success": True,
      "total_expectations": 0,
      "failed_expectations": 0,
    },
    "skew_vs_reference": {},
    "profile_columns": {
      "numeric": _SERVING_NUMERIC_COLS,
      "categorical": _SERVING_CATEGORICAL_COLS,
    },
  }


def _prepare_serving_context(
  args: argparse.Namespace,
  run_dir: Path,
) -> MonitoringContext:
  """Resolve serving-event monitoring inputs and profiling outputs."""
  bucket_name = _resolve_bucket_name(args.bucket_uri)
  backend_url = _resolve_backend_url(args.backend_url)
  export_path = run_dir / "serving_inference_events.jsonl"
  records = _fetch_serving_records(
    backend_url,
    limit=args.serving_export_limit,
  )
  record_count = _write_serving_records(export_path, records)
  baseline_object = (
    _DEFAULT_SERVING_BASELINE_OBJECT
    if args.baseline_object == _DEFAULT_BASELINE_OBJECT
    else args.baseline_object
  )
  reports_prefix = (
    _DEFAULT_SERVING_REPORTS_PREFIX
    if args.reports_prefix == _DEFAULT_REPORTS_PREFIX
    else args.reports_prefix
  )
  current_profile = (
    run_data_profiling(
      data_path=export_path,
      output_dir=run_dir,
      numeric_columns=_SERVING_NUMERIC_COLS,
      categorical_columns=_SERVING_CATEGORICAL_COLS,
    )
    if record_count > 0
    else _empty_serving_profile(export_path)
  )
  return MonitoringContext(
    current_profile=current_profile,
    bucket_name=bucket_name,
    baseline_object=baseline_object,
    latest_report_object=_DEFAULT_SERVING_LATEST_REPORT_OBJECT,
    reports_prefix=reports_prefix,
    baseline_profile=_read_json_blob(bucket_name, baseline_object),
    dataset_id=f"serving-events-{args.runid}",
    dataset_uri=(
      f"{backend_url}/api/v1/inference/monitoring/export?limit={args.serving_export_limit}"
    ),
    dataset_version=args.runid,
  )


def _prepare_gcs_context(
  args: argparse.Namespace,
  run_dir: Path,
) -> MonitoringContext:
  """Resolve Cloud Storage dataset monitoring inputs and profiling outputs."""
  dataset_ref = resolve_cloud_dataset(args.bucket_uri)
  dataset_path = find_downloaded_dataset_file(dataset_ref.local_directory)
  if dataset_path is None:
    msg = f"No transformed dataset found in {dataset_ref.local_directory}"
    raise FileNotFoundError(msg)
  return MonitoringContext(
    current_profile=run_data_profiling(data_path=dataset_path, output_dir=run_dir),
    bucket_name=dataset_ref.bucket_name,
    baseline_object=args.baseline_object,
    latest_report_object=_DEFAULT_LATEST_REPORT_OBJECT,
    reports_prefix=args.reports_prefix,
    baseline_profile=_read_json_blob(dataset_ref.bucket_name, args.baseline_object),
    dataset_id=dataset_ref.dataset_id,
    dataset_uri=dataset_ref.dataset_uri,
    dataset_version=dataset_ref.dataset_version,
  )


def _build_initial_report(
  current_profile: dict[str, Any],
  thresholds: DriftThresholds,
  *,
  monitor_source: str,
) -> dict[str, Any]:
  """Create the first drift report when no prior baseline exists."""
  report: dict[str, Any] = {
    "generated_at": datetime.now(tz=UTC).isoformat(),
    "drift_detected": False,
    "breaches": [],
    "baseline_initialized": True,
    "thresholds": thresholds.to_dict(),
    "baseline_dataset": None,
    "current_dataset": current_profile.get("dataset"),
    "row_count": {
      "baseline": None,
      "current": current_profile.get("row_count"),
      "delta_ratio": 0.0,
      "drifted": False,
    },
    "numeric_drift": {},
    "categorical_drift": {},
    "validation_drift": {
      "baseline_failed_expectations": 0,
      "current_failed_expectations": (
        current_profile.get("ge_validation", {}) or {}
      ).get("failed_expectations", 0),
      "failed_expectations_delta": 0,
      "drifted": False,
    },
  }
  if monitor_source == "serving" and current_profile.get("row_count") == 0:
    report["metadata"] = {"no_serving_events": True}
  return report


def main() -> int:
  """Run the monitoring workflow and persist its artifacts."""
  args = _parse_args()
  run_dir = Paths.models_root / args.runid
  run_dir.mkdir(parents=True, exist_ok=True)
  thresholds = load_drift_thresholds()
  monitor_source = args.monitor_source

  if monitor_source == "serving":
    context = _prepare_serving_context(args, run_dir)
  else:
    context = _prepare_gcs_context(args, run_dir)

  current_profile = context.current_profile
  if context.baseline_profile is None:
    report = _build_initial_report(
      current_profile,
      thresholds,
      monitor_source=monitor_source,
    )
  else:
    report = compare_profile_reports(
      baseline_profile=context.baseline_profile,
      current_profile=current_profile,
      thresholds=thresholds,
    )
    report["baseline_initialized"] = False

  report.update(
    {
      "run_id": args.runid,
      "trigger": args.trigger,
      "trigger_reason": args.trigger_reason,
      "dataset_id": context.dataset_id,
      "dataset_uri": context.dataset_uri,
      "dataset_version": context.dataset_version,
      "bucket_name": context.bucket_name,
      "monitor_source": monitor_source,
      "retrain_recommended": bool(report.get("drift_detected", False)),
    }
  )

  current_profile_object = (
    f"{context.reports_prefix}/{args.runid}/data_profile_report.json"
  )
  drift_report_object = f"{context.reports_prefix}/{args.runid}/drift_report.json"
  report["current_profile_uri"] = _blob_uri(
    context.bucket_name,
    current_profile_object,
  )
  report["drift_report_uri"] = _blob_uri(context.bucket_name, drift_report_object)
  report["latest_profile_uri"] = _blob_uri(
    context.bucket_name,
    context.baseline_object,
  )
  report["latest_drift_report_uri"] = _blob_uri(
    context.bucket_name,
    context.latest_report_object,
  )

  _write_json_blob(
    context.bucket_name,
    current_profile_object,
    current_profile,
  )
  _write_json_blob(
    context.bucket_name,
    context.baseline_object,
    current_profile,
  )
  _write_json_blob(
    context.bucket_name,
    drift_report_object,
    report,
  )
  _write_json_blob(
    context.bucket_name,
    context.latest_report_object,
    report,
  )

  report_path = write_drift_report(run_dir / "drift_report.json", report)
  logger.info("Drift report written to %s", report_path)
  print(json.dumps(report, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
