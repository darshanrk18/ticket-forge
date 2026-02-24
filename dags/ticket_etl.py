"""Airflow DAG that runs ticket ETL (scrape -> transform -> DB load)."""
# ruff: noqa: E402

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException
from airflow.operators.python import get_current_context

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

from training.etl.postload.load_tickets import run_pipeline

DAG_ID = "ticket_etl"


def _require_database_url() -> str:
  """Return DATABASE_URL from env or raise a task failure."""
  dsn = os.environ.get("DATABASE_URL")
  if not dsn:
    msg = "DATABASE_URL is required for ticket_etl DAG."
    raise AirflowFailException(msg)
  return dsn


@task()
def validate_runtime_config() -> dict[str, Any]:
  """Read dag_run.conf and normalize ticket ETL runtime config."""
  context = get_current_context()
  dag_run = context.get("dag_run")
  conf = dag_run.conf if dag_run and dag_run.conf else {}

  raw_limit = conf.get("limit_per_state")
  limit_per_state: int | None = None
  if raw_limit is not None:
    try:
      limit_per_state = int(raw_limit)
    except (TypeError, ValueError) as exc:
      msg = "limit_per_state must be an integer when provided"
      raise AirflowFailException(msg) from exc

  return {
    "dsn": _require_database_url(),
    "limit_per_state": limit_per_state,
  }


@task()
def run_ticket_etl(runtime: dict[str, Any]) -> dict[str, int]:
  """Run scrape -> transform -> tickets/assignments load pipeline."""
  dsn = str(runtime["dsn"])
  limit_per_state_raw = runtime.get("limit_per_state")
  if limit_per_state_raw is None:
    limit_per_state = None
  else:
    limit_per_state = int(limit_per_state_raw)

  loaded = asyncio.run(run_pipeline(dsn=dsn, limit_per_state=limit_per_state))
  return {"tickets_processed": int(loaded)}


@dag(
  dag_id=DAG_ID,
  schedule=None,
  start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
  catchup=False,
  default_args={"owner": "ticketforge", "retries": 1},
  tags=["etl", "airflow", "tickets"],
)
def ticket_etl_dag() -> None:
  """Orchestrate ticket ETL in a dedicated DAG."""
  runtime = validate_runtime_config()
  run_ticket_etl(runtime)


dag = ticket_etl_dag()
