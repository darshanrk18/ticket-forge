resource "google_artifact_registry_repository" "web_backend" {
  location      = var.region
  repository_id = var.web_backend_artifact_registry_repository
  format        = "DOCKER"
  description   = "Backend inference and API images"

  depends_on = [google_project_service.mlflow_services]
}

resource "google_artifact_registry_repository" "web_frontend" {
  location      = var.region
  repository_id = var.web_frontend_artifact_registry_repository
  format        = "DOCKER"
  description   = "Frontend web application images"

  depends_on = [google_project_service.mlflow_services]
}

resource "google_service_account" "web_backend_runtime" {
  account_id   = "web-backend-sa"
  display_name = "TicketForge Backend Runtime"
}

resource "google_service_account" "web_frontend_runtime" {
  account_id   = "web-frontend-sa"
  display_name = "TicketForge Frontend Runtime"
}

resource "google_secret_manager_secret_iam_member" "web_backend_db_password_access" {
  secret_id = google_secret_manager_secret.ticketforge_db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.web_backend_runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "web_backend_jwt_secret_access" {
  secret_id = google_secret_manager_secret.web_backend_jwt_secret_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.web_backend_runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "web_backend_mlflow_admin_password_access" {
  secret_id = google_secret_manager_secret.mlflow_admin_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.web_backend_runtime.email}"
}

resource "google_cloud_run_v2_service" "web_backend" {
  name     = var.web_backend_service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.web_backend_runtime.email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.airflow_vpc.id
        subnetwork = google_compute_subnetwork.airflow_subnet.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.web_backend_image

      ports {
        container_port = 8080
      }

      env {
        name  = "DATABASE_HOST"
        value = google_sql_database_instance.mlflow.private_ip_address
      }

      env {
        name  = "DATABASE_PORT"
        value = "5432"
      }

      env {
        name  = "DATABASE_NAME"
        value = google_sql_database.ticketforge.name
      }

      env {
        name  = "DATABASE_USER"
        value = var.ticketforge_db_user
      }

      env {
        name  = "CORS_ORIGINS"
        value = join(",", var.web_backend_cors_origins)
      }

      env {
        name  = "REFRESH_COOKIE_SECURE"
        value = "true"
      }

      env {
        name  = "REFRESH_COOKIE_SAMESITE"
        value = "none"
      }

      env {
        name  = "MLFLOW_TRACKING_URI"
        value = google_cloud_run_v2_service.mlflow.uri
      }

      env {
        name  = "MLFLOW_REGISTERED_MODEL_NAME"
        value = var.web_backend_mlflow_model_name
      }

      env {
        name  = "MLFLOW_MODEL_STAGE"
        value = var.web_backend_mlflow_model_stage
      }

      env {
        name  = "SERVING_MODEL_VERSION"
        value = var.web_backend_serving_model_version
      }

      env {
        name  = "MLFLOW_TRACKING_USERNAME"
        value = "admin"
      }

      env {
        name = "DATABASE_PASSWORD"

        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.ticketforge_db_password.secret_id
            version = google_secret_manager_secret_version.ticketforge_db_password.version
          }
        }
      }

      env {
        name = "JWT_SECRET_KEY"

        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.web_backend_jwt_secret_key.secret_id
            version = google_secret_manager_secret_version.web_backend_jwt_secret_key.version
          }
        }
      }

      env {
        name = "MLFLOW_TRACKING_PASSWORD"

        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.mlflow_admin_password.secret_id
            version = google_secret_manager_secret_version.mlflow_admin_password.version
          }
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
      }
    }
  }

  deletion_protection = false

  depends_on = [
    google_artifact_registry_repository.web_backend,
    google_secret_manager_secret_version.ticketforge_db_password,
    google_secret_manager_secret_version.web_backend_jwt_secret_key,
    google_secret_manager_secret_version.mlflow_admin_password,
    google_secret_manager_secret_iam_member.web_backend_db_password_access,
    google_secret_manager_secret_iam_member.web_backend_jwt_secret_access,
    google_secret_manager_secret_iam_member.web_backend_mlflow_admin_password_access,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "web_backend_public_invoker" {
  location = google_cloud_run_v2_service.web_backend.location
  name     = google_cloud_run_v2_service.web_backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service" "web_frontend" {
  name     = var.web_frontend_service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.web_frontend_runtime.email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.web_frontend_image

      ports {
        container_port = 8080
      }

      env {
        name  = "NEXT_PUBLIC_API_URL"
        value = var.web_frontend_api_url
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }
  }

  deletion_protection = false

  depends_on = [google_artifact_registry_repository.web_frontend]
}

resource "google_cloud_run_v2_service_iam_member" "web_frontend_public_invoker" {
  location = google_cloud_run_v2_service.web_frontend.location
  name     = google_cloud_run_v2_service.web_frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
