"""Airflow DAG that ingests resume payloads into engineer profiles."""
# ruff: noqa: E402
# noqa

from __future__ import annotations

import base64
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule
from email_callbacks import send_dag_status_email

# Make workspace packages importable from Airflow's DAG context.
REPO_ROOT = Path(__file__).resolve().parent.parent
for path in (
  REPO_ROOT / "apps" / "training",
  REPO_ROOT / "libs" / "ml-core",
  REPO_ROOT / "libs" / "shared",
):
  path_str = str(path)
  if path_str not in sys.path:
    sys.path.append(path_str)

from training.etl.ingest.resume.coldstart import ColdStartManager

DAG_ID = "resume_etl"


def _require_database_url() -> str:
  """Return DATABASE_URL from env or raise a task failure."""
  dsn = os.environ.get("DATABASE_URL")
  if not dsn:
    msg = "DATABASE_URL is required for resume_etl DAG."
    raise AirflowFailException(msg)
  return dsn


def validate_runtime_config(**context: Any) -> dict[str, Any]:
  """Read dag_run.conf and normalize resume payload config."""
  dag_run = context.get("dag_run")
  conf = dag_run.conf if dag_run and dag_run.conf else {}

  resumes = conf.get("resumes", [])
  if resumes is None:
    resumes = []
  if not isinstance(resumes, list):
    msg = "resumes must be an array in dag_run.conf"
    raise AirflowFailException(msg)

  runtime = {
    "dsn": _require_database_url(),
    "resumes": resumes,
  }

  # Push to XCom
  context["task_instance"].xcom_push(key="runtime", value=runtime)
  return runtime


def ingest_resumes_from_conf(**context: Any) -> dict[str, int]:
  """Ingest resume payloads from dag_run.conf into users table profiles."""
  # Pull from XCom
  runtime = context["task_instance"].xcom_pull(
    task_ids="validate_runtime_config", key="runtime"
  )

  resumes = runtime.get("resumes", [])
  if not resumes:
    return {"resumes_processed": 0}

  dsn = str(runtime["dsn"])
  manager = ColdStartManager(dsn=dsn)

  processed = 0
  with tempfile.TemporaryDirectory(prefix="resume_ingest_") as temp_dir:
    temp_root = Path(temp_dir)

    for idx, item in enumerate(resumes):
      if not isinstance(item, dict):
        continue

      filename = str(item.get("filename") or f"resume_{idx}.pdf")
      content_base64 = item.get("content_base64")
      github_username = item.get("github_username")
      full_name = item.get("full_name")

      if not content_base64 or not github_username:
        continue

      try:
        file_bytes = base64.b64decode(content_base64, validate=True)
      except Exception:
        continue

      file_path = temp_root / filename
      file_path.parent.mkdir(parents=True, exist_ok=True)
      file_path.write_bytes(file_bytes)

      profile = manager.process_resume_file(
        str(file_path),
        github_username=str(github_username),
        full_name=str(full_name) if full_name else None,
      )
      manager.save_profile(profile)
      processed += 1

  return {"resumes_processed": processed}


with DAG(
  dag_id=DAG_ID,
  schedule=None,
  start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
  catchup=False,
  default_args={
    "owner": "ticketforge",
    "retries": 0,
  },
  tags=["etl", "airflow", "resumes"],
  max_active_runs=1,
) as dag:
  validate_task = PythonOperator(
    task_id="validate_runtime_config",
    python_callable=validate_runtime_config,
    provide_context=True,
  )

  ingest_task = PythonOperator(
    task_id="ingest_resumes_from_conf",
    python_callable=ingest_resumes_from_conf,
    provide_context=True,
  )

  send_email_task = PythonOperator(
    task_id="send_status_email",
    python_callable=send_dag_status_email,
    provide_context=True,
    trigger_rule=TriggerRule.ALL_DONE,
  )

  validate_task >> ingest_task >> send_email_task
