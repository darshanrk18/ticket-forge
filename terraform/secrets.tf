resource "random_password" "airflow_admin_password" {
  length  = 24
  special = false
}

resource "random_password" "airflow_webserver_secret_key" {
  length  = 64
  special = false
}

resource "random_password" "web_backend_jwt_secret_key" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret" "airflow_admin_password" {
  secret_id = "airflow-admin-password-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.airflow_services]
}

resource "google_secret_manager_secret_version" "airflow_admin_password" {
  secret      = google_secret_manager_secret.airflow_admin_password.id
  secret_data = coalesce(var.airflow_admin_password, random_password.airflow_admin_password.result)
}

resource "google_secret_manager_secret" "airflow_webserver_secret_key" {
  secret_id = var.airflow_webserver_secret_key_secret_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.airflow_services]
}

resource "google_secret_manager_secret_version" "airflow_webserver_secret_key" {
  secret      = google_secret_manager_secret.airflow_webserver_secret_key.id
  secret_data = coalesce(var.airflow_webserver_secret_key, random_password.airflow_webserver_secret_key.result)
}

resource "google_secret_manager_secret" "airflow_db_password" {
  secret_id = "airflow-db-password-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.airflow_services]
}

resource "google_secret_manager_secret_version" "airflow_db_password" {
  secret      = google_secret_manager_secret.airflow_db_password.id
  secret_data = coalesce(var.airflow_db_password, random_password.airflow_db_password.result)
}

resource "google_secret_manager_secret" "ticketforge_db_password" {
  secret_id = "ticketforge-db-password-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.airflow_services]
}

resource "google_secret_manager_secret_version" "ticketforge_db_password" {
  secret      = google_secret_manager_secret.ticketforge_db_password.id
  secret_data = coalesce(var.ticketforge_db_password, random_password.ticketforge_db_password.result)
}

resource "google_secret_manager_secret" "web_backend_jwt_secret_key" {
  secret_id = var.web_backend_jwt_secret_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.airflow_services]
}

resource "google_secret_manager_secret_version" "web_backend_jwt_secret_key" {
  secret      = google_secret_manager_secret.web_backend_jwt_secret_key.id
  secret_data = coalesce(var.web_backend_jwt_secret_key, random_password.web_backend_jwt_secret_key.result)
}

locals {
  airflow_runtime_secret_ids = {
    github_token       = var.airflow_github_token_secret_id
    gmail_app_username = var.airflow_gmail_app_username_secret_id
    gmail_app_password = var.airflow_gmail_app_password_secret_id
  }
}

resource "google_secret_manager_secret" "airflow_runtime" {
  for_each  = local.airflow_runtime_secret_ids
  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.airflow_services]
}

locals {
  airflow_admin_password        = coalesce(var.airflow_admin_password, random_password.airflow_admin_password.result)
  airflow_db_password_value     = coalesce(var.airflow_db_password, random_password.airflow_db_password.result)
  ticketforge_db_password_value = coalesce(var.ticketforge_db_password, random_password.ticketforge_db_password.result)
  airflow_sqlalchemy_conn = format(
    "postgresql+psycopg2://%s:%s@%s/%s",
    var.airflow_db_user,
    local.airflow_db_password_value,
    google_sql_database_instance.mlflow.private_ip_address,
    var.airflow_db_name,
  )
  ticketforge_sqlalchemy_conn = format(
    "postgresql://%s:%s@%s/%s",
    var.ticketforge_db_user,
    local.ticketforge_db_password_value,
    google_sql_database_instance.mlflow.private_ip_address,
    var.ticketforge_db_name,
  )
}
