"""Static checks for Cloud SQL terraform idempotency-oriented settings."""

from pathlib import Path


def test_cloud_sql_tf_has_expected_resources() -> None:
  """Cloud SQL file declares shared instance plus airflow db/user resources."""
  tf_content = Path("terraform/cloud_sql.tf").read_text(encoding="utf-8")

  assert 'resource "google_sql_database_instance" "mlflow"' in tf_content
  assert 'resource "google_sql_database" "airflow"' in tf_content
  assert 'resource "google_sql_user" "airflow"' in tf_content
  assert "backup_configuration" in tf_content
