"""Airflow DAG that runs ticket ETL pipeline starting from all_tickets.json."""
# ruff: noqa: E402
# noqa

from __future__ import annotations

import gzip
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule
from email_callbacks import send_dag_status_email
from shared.configuration import Paths

REPO_ROOT = Path(__file__).resolve().parent.parent
for path in (
  REPO_ROOT / "apps" / "training",
  REPO_ROOT / "libs" / "ml-core",
  REPO_ROOT / "libs" / "shared",
):
  path_str = str(path)
  if path_str not in sys.path:
    sys.path.append(path_str)

DAG_ID = "ticket_etl_from_file"

# ---- INPUT FILE ----
INPUT_RAW_PATH = Paths.data_root / "github_issues" / "all_tickets.json"


def _require_database_url() -> str:
  """Return DATABASE_URL from env or raise a task failure."""
  dsn = os.environ.get("DATABASE_URL")
  if not dsn:
    msg = "DATABASE_URL is required for ticket_etl_from_file DAG."
    raise AirflowFailException(msg)
  return dsn


def _require_gcs_bucket_uri() -> str:
  """Return normalized GCS_BUCKET_NAME URI from env or raise a task failure."""
  bucket_uri = os.environ.get("GCS_BUCKET_NAME")
  if not bucket_uri:
    msg = "GCS_BUCKET_NAME is required for ticket_etl_from_file DAG."
    raise AirflowFailException(msg)

  normalized = bucket_uri.strip()
  if not normalized.startswith("gs://"):
    msg = "GCS_BUCKET_NAME must use gs://<bucket> format."
    raise AirflowFailException(msg)

  bucket_name = normalized.removeprefix("gs://").strip("/")
  if not bucket_name or "/" in bucket_name:
    msg = "GCS_BUCKET_NAME must include only a bucket name (no object path)."
    raise AirflowFailException(msg)

  return f"gs://{bucket_name}"


def validate_runtime_config(**context: object) -> dict[str, Any]:
  """Validate the input file exists and set up output directory."""
  if not INPUT_RAW_PATH.exists():
    msg = f"Input file not found: {INPUT_RAW_PATH}"
    raise AirflowFailException(msg)

  run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
  output_dir = Paths.data_root / f"github_issues-{run_timestamp}"
  output_dir.mkdir(parents=True, exist_ok=True)

  runtime = {
    "dsn": _require_database_url(),
    "gcs_bucket_uri": _require_gcs_bucket_uri(),
    "output_dir": str(output_dir),
    "run_timestamp": run_timestamp,
  }

  print(f"Using input file: {INPUT_RAW_PATH}")
  print(f"Output directory: {output_dir}")

  context["task_instance"].xcom_push(key="runtime", value=runtime)  # type: ignore[index, union-attr]
  return runtime


def run_transform(**context: object) -> dict[str, Any]:
  """Transform raw records from all_tickets.json into ticket features."""
  from training.etl.transform.run_transform import transform_records

  runtime = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="validate_runtime_config", key="runtime"
  )
  output_dir = Path(runtime["output_dir"])

  print(f"Loading raw data from {INPUT_RAW_PATH}...")
  with open(INPUT_RAW_PATH, encoding="utf-8") as f:
    raw_records = json.load(f)
  print(f"Loaded {len(raw_records):,} raw records")

  print(f"Transforming {len(raw_records):,} records...")
  transformed = transform_records(raw_records)
  print(f"Transformed {len(transformed):,} records")

  transform_path = output_dir / "tickets_transformed_improved.jsonl"
  with open(transform_path, "w", encoding="utf-8") as f:
    for record in transformed:
      f.write(json.dumps(record) + "\n")
  print(f"Saved transformed data to {transform_path}")

  context["task_instance"].xcom_push(key="transform_path", value=str(transform_path))  # type: ignore[index, union-attr]
  return {"records_transformed": len(transformed)}


def run_data_profiling_task(**context: object) -> dict[str, Any]:
  """Run data profiling on transformed data (non-blocking)."""
  from training.analysis.run_data_profiling import run_data_profiling

  runtime = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="validate_runtime_config", key="runtime"
  )
  transform_path = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="run_transform", key="transform_path"
  )
  output_dir = runtime["output_dir"]

  try:
    result = run_data_profiling(data_path=transform_path, output_dir=output_dir)
    print("Data profiling complete!")
    return {"profiling_done": True, "row_count": result["row_count"]}
  except Exception as e:  # noqa: BLE001
    print("Data profiling failed (non-blocking):", str(e))
    return {"profiling_done": False, "error": str(e)}


def run_anomaly_check(**context: object) -> dict[str, Any]:
  """Run anomaly detection on transformed data (non-blocking with alerting)."""
  from email_callbacks import send_dag_status_email
  from training.analysis.run_anomaly_check import run_anomaly_check as analyze_anomaly

  transform_path = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="run_transform", key="transform_path"
  )

  results = analyze_anomaly(
    data_path=transform_path,
    outlier_threshold=3.0,
    enable_alerts=False,
  )

  anomaly_report = results["anomaly_report"]
  schema_issues = results["schema_result"]["num_amiss"]
  anomaly_text = results["text_report"]

  print(anomaly_text)

  total_anomalies = anomaly_report["total_anomalies"]

  anomaly_warn_threshold = 20
  schema_warn_threshold = 5

  if total_anomalies > anomaly_warn_threshold or schema_issues > schema_warn_threshold:
    print(
      f"⚠ WARNING: High anomaly count detected "
      f"(anomalies={total_anomalies}, schema_issues={schema_issues})"
    )
    send_dag_status_email(
      additional_text=anomaly_text,
      subject_override="TicketForge: Anomaly Warning (Pipeline Continuing)",
      **context,
    )
  else:
    print("Anomaly levels within acceptable range.")

  context["task_instance"].xcom_push(key="anomaly_report", value=anomaly_report)  # type: ignore[index, union-attr]
  context["task_instance"].xcom_push(key="anomaly_email_text", value=anomaly_text)  # type: ignore[index, union-attr]

  return {
    "anomalies_detected": anomaly_report["has_anomalies"],
    "total_anomalies": total_anomalies,
    "schema_issues": schema_issues,
  }


def run_bias_detection(**context: object) -> dict[str, Any]:
  """Run bias detection analysis on transformed data."""
  from training.analysis.detect_bias import run_bias_detection as analyze_bias

  print("Starting bias detection analysis...")

  transform_path = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="run_transform", key="transform_path"
  )

  bias_detection_report = analyze_bias(transform_path)

  context["task_instance"].xcom_push(  # type: ignore[index, union-attr]
    key="bias_detection_report", value=bias_detection_report
  )
  print("Bias detection analysis complete!")
  return {"bias_detection_done": True}


def run_bias_mitigation(**context: object) -> dict[str, Any]:
  """Run bias mitigation (sample weights mode) on timestamped data."""
  from training.analysis.run_bias_mitigation import run_bias_mitigation_weights

  print("Starting bias mitigation...")

  transform_path = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="run_transform", key="transform_path"
  )
  runtime = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="validate_runtime_config", key="runtime"
  )

  output_dir = runtime["output_dir"]

  mitigation_results = run_bias_mitigation_weights(
    data_path=transform_path, output_dir=output_dir
  )

  context["task_instance"].xcom_push(  # type: ignore[index, union-attr]
    key="bias_mitigation_results", value=mitigation_results
  )
  context["task_instance"].xcom_push(  # type: ignore[index, union-attr]
    key="weights_path", value=mitigation_results["weights_path"]
  )

  print("Bias mitigation complete!")
  return {"bias_mitigation_done": True}


def prepare_bias_report(**context: object) -> dict[str, Any]:
  """Combine bias detection and mitigation results into a detailed report."""
  from training.analysis.detect_bias import generate_bias_report_text

  bias_detection_report = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="run_bias_detection", key="bias_detection_report"
  )
  bias_mitigation_results = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="run_bias_mitigation", key="bias_mitigation_results"
  )

  combined_report = {**bias_detection_report}
  combined_report["weights_by_group"] = bias_mitigation_results.get(
    "weights_by_group", {}
  )

  report_text = generate_bias_report_text(
    bias_detection_report, bias_mitigation_results
  )
  print("\n" + report_text + "\n")

  combined_report["text_report"] = report_text

  context["task_instance"].xcom_push(key="combined_bias_report", value=combined_report)  # type: ignore[index, union-attr]
  context["task_instance"].xcom_push(key="bias_email_text", value=report_text)  # type: ignore[index, union-attr]
  return combined_report


def save_dataset_and_weights(**context: object) -> dict[str, Any]:
  """Save transformed dataset (compressed) and bias mitigation weights."""
  print("Saving dataset and weights...")

  runtime = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="validate_runtime_config", key="runtime"
  )
  transform_path = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="run_transform", key="transform_path"
  )
  weights_path = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="run_bias_mitigation", key="weights_path"
  )
  anomaly_text = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="run_anomaly_check", key="anomaly_email_text"
  )
  bias_text = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="prepare_bias_report", key="bias_email_text"
  )

  output_dir = Path(runtime["output_dir"])

  compressed_path = output_dir / "tickets_transformed_improved.jsonl.gz"
  print("Compressing dataset to", compressed_path)

  with open(transform_path, "rb") as f_in:
    with gzip.open(compressed_path, "wb") as f_out:
      f_out.writelines(f_in)

  print("Saved compressed dataset to", compressed_path)

  if Path(weights_path).exists():
    print("Bias mitigation weights already saved at", weights_path)
  else:
    msg = "Bias mitigation weights not found at " + str(weights_path)
    raise AirflowFailException(msg)

  result: dict[str, Any] = {
    "dataset_saved": str(compressed_path),
    "weights_saved": str(weights_path),
  }

  if anomaly_text:
    anomaly_report_path = output_dir / "anomaly_report.txt"
    with open(anomaly_report_path, "w", encoding="utf-8") as f:
      f.write(anomaly_text)
    print("Saved anomaly report to", anomaly_report_path)
    result["anomaly_report_saved"] = str(anomaly_report_path)

  if bias_text:
    bias_report_path = output_dir / "bias_report.txt"
    with open(bias_report_path, "w", encoding="utf-8") as f:
      f.write(bias_text)
    print("Saved bias report to", bias_report_path)
    result["bias_report_saved"] = str(bias_report_path)

  return result


def upload_output_dir_to_gcs(**context: object) -> dict[str, Any]:
  """Upload full run output directory to GCS and update index.json."""
  from training.etl.postload.publish_ticket_etl_output import publish_ticket_etl_output

  runtime = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="validate_runtime_config", key="runtime"
  )

  output_dir = Path(str(runtime["output_dir"]))
  run_timestamp = str(runtime["run_timestamp"])
  bucket_uri = str(runtime["gcs_bucket_uri"])

  result = publish_ticket_etl_output(
    output_dir=output_dir,
    bucket_uri=bucket_uri,
    run_timestamp=run_timestamp,
  )

  print("Uploaded", result["object_count"], "artifact(s) to", result["object_prefix"])
  print("Updated dataset index at", result["index_uri"])
  return result


def load_tickets_to_db(**context: object) -> dict[str, int]:
  """Load transformed tickets and assignments into Postgres."""
  from training.etl.ingest.resume.coldstart import ensure_profiles_for_tickets
  from training.etl.postload.load_tickets import upsert_assignments, upsert_tickets

  runtime = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="validate_runtime_config", key="runtime"
  )
  transform_path = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="run_transform", key="transform_path"
  )
  dsn = str(runtime["dsn"])

  print("Loading transformed data from", transform_path)
  transformed = []
  with open(transform_path, encoding="utf-8") as f:
    for line in f:
      if line.strip():
        transformed.append(json.loads(line))
  print("Loaded", len(transformed), "transformed records")

  print("Step 0/2: Ensuring assignee profiles exist...")
  profile_results = ensure_profiles_for_tickets(transformed, dsn=dsn)
  print("Ensured", len(profile_results), "profile(s) for ticket assignees")

  print("Step 1/2: Upserting tickets...")
  loaded_tickets = upsert_tickets(transformed, dsn=dsn)
  print("Upserted", loaded_tickets, "ticket(s) into Postgres")

  print("Step 2/2: Upserting assignments...")
  assigned_count, missing_user_count = upsert_assignments(transformed, dsn=dsn)
  print("Upserted", assigned_count, "assignment row(s)")
  if missing_user_count:
    print("Skipped", missing_user_count, "assignment(s): assignee not found in users")

  return {
    "tickets_loaded": loaded_tickets,
    "assignments_upserted": assigned_count,
  }


def replay_closed_tickets(**context: object) -> dict[str, int]:
  """Replay newly imported closed tickets to update engineer profiles."""
  from training.etl.postload.replay_tickets import TicketReplayer

  runtime = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="validate_runtime_config", key="runtime"
  )
  transform_path = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
    task_ids="run_transform", key="transform_path"
  )
  dsn = str(runtime["dsn"])

  print("Loading transformed data from", transform_path)
  transformed = []
  with open(transform_path, encoding="utf-8") as f:
    for line in f:
      if line.strip():
        transformed.append(json.loads(line))
  print("Loaded", len(transformed), "transformed records")

  closed_ticket_ids = [
    str(t.get("id")) for t in transformed if t.get("issue_type") == "closed"
  ]

  if not closed_ticket_ids:
    print("No closed tickets to replay")
    return {"tickets_replayed": 0}

  print("Replaying", len(closed_ticket_ids), "closed tickets...")
  replayer = TicketReplayer(dsn=dsn)
  replayed_count = replayer.replay(closed_ticket_ids)
  print("Replayed", replayed_count, "closed ticket assignment(s)")

  return {"tickets_replayed": replayed_count}


with DAG(
  dag_id=DAG_ID,
  schedule=None,
  start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
  catchup=False,
  default_args={
    "owner": "ticketforge",
    "retries": 0,
  },
  max_active_runs=1,
  tags=["etl", "airflow", "tickets", "from-file"],
) as dag:
  validate_task = PythonOperator(
    task_id="validate_runtime_config",
    python_callable=validate_runtime_config,
    provide_context=True,
  )

  transform_task = PythonOperator(
    task_id="run_transform",
    python_callable=run_transform,
    provide_context=True,
  )

  profiling_task = PythonOperator(
    task_id="run_data_profiling",
    python_callable=run_data_profiling_task,
    provide_context=True,
  )

  anomaly_task = PythonOperator(
    task_id="run_anomaly_check",
    python_callable=run_anomaly_check,
    provide_context=True,
  )

  bias_detect_task = PythonOperator(
    task_id="run_bias_detection",
    python_callable=run_bias_detection,
    provide_context=True,
  )

  bias_mitigate_task = PythonOperator(
    task_id="run_bias_mitigation",
    python_callable=run_bias_mitigation,
    provide_context=True,
  )

  prepare_report_task = PythonOperator(
    task_id="prepare_bias_report",
    python_callable=prepare_bias_report,
    provide_context=True,
  )

  save_task = PythonOperator(
    task_id="save_dataset_and_weights",
    python_callable=save_dataset_and_weights,
    provide_context=True,
  )

  load_db_task = PythonOperator(
    task_id="load_tickets_to_db",
    python_callable=load_tickets_to_db,
    provide_context=True,
  )

  replay_task = PythonOperator(
    task_id="replay_closed_tickets",
    python_callable=replay_closed_tickets,
    provide_context=True,
  )

  upload_task = PythonOperator(
    task_id="upload_output_dir_to_gcs",
    python_callable=upload_output_dir_to_gcs,
    provide_context=True,
  )

  def send_email_with_report(**context: object) -> None:
    """Send email with bias report."""
    anomaly_text = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
      task_ids="run_anomaly_check", key="anomaly_email_text"
    )
    bias_text = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
      task_ids="prepare_bias_report", key="bias_email_text"
    )
    upload_summary = context["task_instance"].xcom_pull(  # type: ignore[index, union-attr]
      task_ids="upload_output_dir_to_gcs"
    )

    additional_parts = [text for text in [anomaly_text, bias_text] if text]
    if isinstance(upload_summary, dict):
      dataset_uri = upload_summary.get("dataset_uri")
      index_uri = upload_summary.get("index_uri")
      if isinstance(dataset_uri, str) and isinstance(index_uri, str):
        additional_parts.append(
          f"Cloud dataset published:\n- Dataset: {dataset_uri}\n- Index: {index_uri}"
        )

    additional_text = "\n\n".join(additional_parts) if additional_parts else None

    send_dag_status_email(additional_text=additional_text, **context)

  send_email_task = PythonOperator(
    task_id="send_status_email",
    python_callable=send_email_with_report,
    provide_context=True,
    trigger_rule=TriggerRule.ALL_DONE,
  )

  # Validate -> Transform -> [Anomaly, Profiling] (parallel)
  _ = validate_task >> transform_task >> anomaly_task

  # Anomaly -> Bias Detection & Mitigation (parallel)
  _ = (
    anomaly_task
    >> profiling_task
    >> [bias_detect_task, bias_mitigate_task]
    >> prepare_report_task
    >> save_task
    >> upload_task
  )

  # Anomaly -> Load to DB -> Replay (independent of bias path)
  _ = anomaly_task >> load_db_task >> replay_task

  # All paths converge before publication, then email.
  _ = [upload_task, replay_task] >> send_email_task
