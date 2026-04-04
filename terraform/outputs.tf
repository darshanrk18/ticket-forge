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
