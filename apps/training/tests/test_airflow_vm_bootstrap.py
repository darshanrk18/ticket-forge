"""Smoke tests for Airflow VM bootstrap template invariants."""

from pathlib import Path


def test_airflow_startup_template_contains_required_commands() -> None:
  """Startup template includes clone, Airflow startup, and env wiring."""
  template_path = Path("terraform/templates/airflow_startup.sh.tftpl")
  content = template_path.read_text(encoding="utf-8")

  assert "git clone" in content
  assert "run_airflow.sh" in content
  assert "airflow webserver" in content
  assert "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN" in content
  assert "GCS_BUCKET_NAME" in content
