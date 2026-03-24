output "mlflow_tracking_uri" {
  description = "Private MLflow tracking URI hosted on Cloud Run."
  value       = google_cloud_run_v2_service.mlflow.uri
}

output "mlflow_tracking_audience" {
  description = "Audience for minting Cloud Run identity tokens."
  value       = google_cloud_run_v2_service.mlflow.uri
}

output "mlflow_service_account_email" {
  description = "Service account used by the MLflow Cloud Run service."
  value       = google_service_account.mlflow_server.email
}
