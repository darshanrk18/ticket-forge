resource "google_project_service" "mlflow_services" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "vpcaccess.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

locals {
  default_mlflow_image = format(
    "%s-docker.pkg.dev/%s/%s/mlflow-gcp:%s",
    var.region,
    var.project_id,
    var.mlflow_artifact_registry_repository,
    var.mlflow_image_tag,
  )
  effective_mlflow_image = coalesce(var.mlflow_server_image, local.default_mlflow_image)
}

resource "google_artifact_registry_repository" "mlflow" {
  location      = var.region
  repository_id = var.mlflow_artifact_registry_repository
  format        = "DOCKER"
  description   = "MLflow server image repository"

  depends_on = [google_project_service.mlflow_services]
}

resource "google_service_account" "mlflow_server" {
  account_id   = "mlflow-server-sa"
  display_name = "MLflow Tracking Service"
}

resource "google_project_iam_member" "mlflow_server_cloudsql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.mlflow_server.email}"
}

resource "google_storage_bucket_iam_member" "mlflow_artifacts_access" {
  bucket = var.data_bucket
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.mlflow_server.email}"
}

resource "random_password" "mlflow_flask_secret_key" {
  length  = 64
  special = false
}

resource "random_password" "mlflow_admin_password" {
  length  = 32
  special = false
}

resource "google_secret_manager_secret" "mlflow_flask_secret_key" {
  secret_id = "${var.mlflow_service_name}-flask-secret-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.mlflow_services]
}

resource "google_secret_manager_secret_version" "mlflow_flask_secret_key" {
  secret      = google_secret_manager_secret.mlflow_flask_secret_key.id
  secret_data = random_password.mlflow_flask_secret_key.result
}

resource "google_secret_manager_secret" "mlflow_admin_password" {
  secret_id = "${var.mlflow_service_name}-admin-password"

  replication {
    auto {}
  }

  depends_on = [google_project_service.mlflow_services]
}

resource "google_secret_manager_secret_version" "mlflow_admin_password" {
  secret      = google_secret_manager_secret.mlflow_admin_password.id
  secret_data = random_password.mlflow_admin_password.result
}

resource "google_secret_manager_secret_iam_member" "mlflow_server_secret_access" {
  secret_id = google_secret_manager_secret.mlflow_db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.mlflow_server.email}"
}

resource "google_secret_manager_secret_iam_member" "mlflow_server_flask_secret_access" {
  secret_id = google_secret_manager_secret.mlflow_flask_secret_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.mlflow_server.email}"
}

resource "google_secret_manager_secret_iam_member" "mlflow_server_admin_password_access" {
  secret_id = google_secret_manager_secret.mlflow_admin_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.mlflow_server.email}"
}

resource "google_cloud_run_v2_service" "mlflow" {
  name     = var.mlflow_service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    max_instance_request_concurrency = 100
    service_account                  = google_service_account.mlflow_server.email
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

    volumes {
      name = "cloudsql"

      cloud_sql_instance {
        instances = [google_sql_database_instance.mlflow.connection_name]
      }
    }

    containers {
      image   = local.effective_mlflow_image
      command = ["/bin/sh", "-c"]

      args = [
        "cat > /tmp/basic_auth.ini <<EOF\n[mlflow]\ndefault_permission = READ\ndatabase_uri = postgresql+psycopg2://${var.mlflow_db_user}:$${MLFLOW_DB_PASSWORD}@/${google_sql_database.mlflow.name}?host=/cloudsql/${google_sql_database_instance.mlflow.connection_name}\nadmin_username = admin\nadmin_password = $${MLFLOW_ADMIN_PASSWORD}\nEOF\nexport MLFLOW_AUTH_CONFIG_PATH=/tmp/basic_auth.ini\nexec mlflow server --host 0.0.0.0 --port 5000 --app-name basic-auth --allowed-hosts \"*\" --cors-allowed-origins \"*\" --backend-store-uri \"postgresql+psycopg2://${var.mlflow_db_user}:$${MLFLOW_DB_PASSWORD}@/${google_sql_database.mlflow.name}?host=/cloudsql/${google_sql_database_instance.mlflow.connection_name}\" --artifacts-destination \"gs://${var.data_bucket}/mlflow-artifacts\"",
      ]

      ports {
        container_port = 5000
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name  = "MLFLOW_AUTH_MODE"
        value = "basic-auth"
      }

      env {
        name = "MLFLOW_FLASK_SERVER_SECRET_KEY"

        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.mlflow_flask_secret_key.secret_id
            version = google_secret_manager_secret_version.mlflow_flask_secret_key.version
          }
        }
      }

      env {
        name = "MLFLOW_DB_PASSWORD"

        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.mlflow_db_password.secret_id
            version = google_secret_manager_secret_version.mlflow_db_password.version
          }
        }
      }

      env {
        name = "MLFLOW_ADMIN_PASSWORD"

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
    google_project_service.mlflow_services,
    google_artifact_registry_repository.mlflow,
    google_sql_database.mlflow,
    google_sql_user.mlflow,
    google_secret_manager_secret_version.mlflow_db_password,
    google_secret_manager_secret_version.mlflow_flask_secret_key,
    google_secret_manager_secret_version.mlflow_admin_password,
    google_secret_manager_secret_iam_member.mlflow_server_secret_access,
    google_secret_manager_secret_iam_member.mlflow_server_flask_secret_access,
    google_secret_manager_secret_iam_member.mlflow_server_admin_password_access,
    google_project_iam_member.mlflow_server_cloudsql,
    google_storage_bucket_iam_member.mlflow_artifacts_access,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "ml_pipeline_invoker" {
  location = google_cloud_run_v2_service.mlflow.location
  name     = google_cloud_run_v2_service.mlflow.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.ml_pipeline.email}"
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  location = google_cloud_run_v2_service.mlflow.location
  name     = google_cloud_run_v2_service.mlflow.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "additional_invokers" {
  for_each = toset(var.mlflow_additional_invokers)

  location = google_cloud_run_v2_service.mlflow.location
  name     = google_cloud_run_v2_service.mlflow.name
  role     = "roles/run.invoker"
  member   = each.value
}
