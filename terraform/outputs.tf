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

output "web_backend_service_name" {
  description = "Cloud Run service name for the production backend."
  value       = google_cloud_run_v2_service.web_backend.name
}

output "web_backend_service_url" {
  description = "Public URL for the production backend API."
  value       = google_cloud_run_v2_service.web_backend.uri
}

output "web_backend_service_account_email" {
  description = "Service account used by the production backend."
  value       = google_service_account.web_backend_runtime.email
}

output "web_backend_artifact_registry_repository" {
  description = "Artifact Registry repository for backend images."
  value       = google_artifact_registry_repository.web_backend.repository_id
}

output "web_frontend_service_name" {
  description = "Cloud Run service name for the production frontend."
  value       = google_cloud_run_v2_service.web_frontend.name
}

output "web_frontend_service_url" {
  description = "Public URL for the production frontend."
  value       = google_cloud_run_v2_service.web_frontend.uri
}

output "web_frontend_service_account_email" {
  description = "Service account used by the production frontend."
  value       = google_service_account.web_frontend_runtime.email
}

output "web_frontend_artifact_registry_repository" {
  description = "Artifact Registry repository for frontend images."
  value       = google_artifact_registry_repository.web_frontend.repository_id
}

output "airflow_vm_instance_name" {
  description = "Name of the Airflow Compute Engine VM."
  value       = google_compute_instance.airflow_vm.name
}

output "airflow_vm_internal_ip" {
  description = "Internal IP of the Airflow VM."
  value       = google_compute_instance.airflow_vm.network_interface[0].network_ip
}

output "airflow_webserver_url" {
  description = "Internal Airflow webserver URL. Access via: gcloud compute start-iap-tunnel <instance-name> 8080"
  value       = "http://${google_compute_instance.airflow_vm.network_interface[0].network_ip}:8080"
}

output "cloud_sql_instance_connection_name" {
  description = "Cloud SQL connection name for the shared Airflow/MLflow/ticketforge instance."
  value       = google_sql_database_instance.mlflow.connection_name
}

output "cloud_sql_private_ip" {
  description = "Cloud SQL private IP address."
  value       = google_sql_database_instance.mlflow.private_ip_address
}

output "cloud_sql_database_name" {
  description = "Cloud SQL database name used by Airflow."
  value       = google_sql_database.airflow.name
}

output "cloud_sql_ticketforge_database_name" {
  description = "Cloud SQL database name used by ticket-forge application tables."
  value       = google_sql_database.ticketforge.name
}

output "cloud_sql_ticketforge_database_user" {
  description = "Cloud SQL username used by ticket-forge application tables."
  value       = var.ticketforge_db_user
}

output "cloud_sql_mlflow_database_name" {
  description = "Cloud SQL database name used by MLflow backend store."
  value       = google_sql_database.mlflow.name
}

output "training_bucket_name" {
  description = "Cloud Storage bucket name used for training datasets and artifacts."
  value       = google_storage_bucket.training_artifacts.name
}

output "training_bucket_gs_uri" {
  description = "Cloud Storage URI for training datasets and artifacts."
  value       = "gs://${google_storage_bucket.training_artifacts.name}"
}

output "airflow_service_account_email" {
  description = "Service account used by the Airflow runtime VM."
  value       = google_service_account.airflow_runtime.email
}

output "vpc_network_name" {
  description = "VPC used by Airflow and Cloud SQL private connectivity."
  value       = google_compute_network.airflow_vpc.name
}

output "terraform_state_bucket_name" {
  description = "Bucket used for Terraform state backend configuration."
  value       = var.state_bucket
}

output "ticketforge_api_uri" {
  description = "Public HTTPS URL for the TicketForge API Cloud Run service when app serving is enabled."
  value       = length(google_cloud_run_v2_service.ticketforge_api) > 0 ? google_cloud_run_v2_service.ticketforge_api[0].uri : null
}

output "ticketforge_inference_uri" {
  description = "Public HTTPS URL for the TicketForge inference Cloud Run service when app serving is enabled."
  value       = length(google_cloud_run_v2_service.ticketforge_inference) > 0 ? google_cloud_run_v2_service.ticketforge_inference[0].uri : null
}

output "ticketforge_web_uri" {
  description = "Public HTTPS URL for the TicketForge web Cloud Run service when app serving is enabled."
  value       = length(google_cloud_run_v2_service.ticketforge_web) > 0 ? google_cloud_run_v2_service.ticketforge_web[0].uri : null
}

output "ticketforge_api_service_account_email" {
  description = "Runtime service account for the API Cloud Run service when app serving is enabled."
  value       = length(google_service_account.ticketforge_api) > 0 ? google_service_account.ticketforge_api[0].email : null
}
