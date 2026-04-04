

resource "random_password" "airflow_db_password" {
  length  = 32
  special = false
}

resource "random_password" "ticketforge_db_password" {
  length  = 32
  special = false
}

resource "random_password" "mlflow_db_password" {
  # MLflow receives this via backend-store URI userinfo; keep it URL-safe.
  length  = 32
  special = false
}

resource "google_sql_database_instance" "mlflow" {
  name             = var.shared_cloud_sql_instance_name
  region           = var.region
  database_version = "POSTGRES_15"

  settings {
    tier              = var.mlflow_db_tier
    availability_type = "ZONAL"
    disk_size         = 40
    disk_type         = "PD_SSD"

    backup_configuration {
      enabled = true
    }

    dynamic "database_flags" {
      for_each = var.cloud_sql_max_connections == null ? [] : [var.cloud_sql_max_connections]
      content {
        name  = "max_connections"
        value = tostring(database_flags.value)
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.airflow_vpc.id
    }
  }

  deletion_protection = true
  depends_on = [
    google_project_service.mlflow_services,
    google_service_networking_connection.private_vpc_connection,
  ]
}

resource "google_sql_database" "airflow" {
  name     = var.airflow_db_name
  instance = google_sql_database_instance.mlflow.name
}

resource "google_sql_database" "ticketforge" {
  name     = var.ticketforge_db_name
  instance = google_sql_database_instance.mlflow.name
}

resource "google_sql_database" "mlflow" {
  name     = var.mlflow_db_name
  instance = google_sql_database_instance.mlflow.name
}

resource "google_sql_user" "airflow" {
  instance = google_sql_database_instance.mlflow.name
  name     = var.airflow_db_user
  password = coalesce(var.airflow_db_password, random_password.airflow_db_password.result)
}

resource "google_sql_user" "ticketforge" {
  instance = google_sql_database_instance.mlflow.name
  name     = var.ticketforge_db_user
  password = coalesce(var.ticketforge_db_password, random_password.ticketforge_db_password.result)
}

resource "google_sql_user" "mlflow" {
  instance = google_sql_database_instance.mlflow.name
  name     = var.mlflow_db_user
  password = random_password.mlflow_db_password.result
}

resource "google_secret_manager_secret" "mlflow_db_password" {
  secret_id = "${var.mlflow_service_name}-db-password"

  replication {
    auto {}
  }

  depends_on = [google_project_service.mlflow_services]
}

resource "google_secret_manager_secret_version" "mlflow_db_password" {
  secret      = google_secret_manager_secret.mlflow_db_password.id
  secret_data = random_password.mlflow_db_password.result
}
