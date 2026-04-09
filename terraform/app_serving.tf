locals {
  ticketforge_async_database_url = format(
    "postgresql+asyncpg://%s:%s@%s:5432/%s",
    var.ticketforge_db_user,
    urlencode(local.ticketforge_db_password_value),
    google_sql_database_instance.mlflow.private_ip_address,
    var.ticketforge_db_name,
  )
}

resource "random_password" "ticketforge_api_jwt" {
  count   = var.enable_ticketforge_app_cloud_run ? 1 : 0
  length  = 48
  special = false
}

resource "google_secret_manager_secret" "ticketforge_api_jwt" {
  count     = var.enable_ticketforge_app_cloud_run ? 1 : 0
  secret_id = "ticketforge-api-jwt-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.mlflow_services]
}

resource "google_secret_manager_secret_version" "ticketforge_api_jwt" {
  count       = var.enable_ticketforge_app_cloud_run ? 1 : 0
  secret      = google_secret_manager_secret.ticketforge_api_jwt[0].id
  secret_data = random_password.ticketforge_api_jwt[0].result
}

resource "google_secret_manager_secret" "ticketforge_api_database_url" {
  count     = var.enable_ticketforge_app_cloud_run ? 1 : 0
  secret_id = "ticketforge-api-database-url-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.mlflow_services]
}

resource "google_secret_manager_secret_version" "ticketforge_api_database_url" {
  count       = var.enable_ticketforge_app_cloud_run ? 1 : 0
  secret      = google_secret_manager_secret.ticketforge_api_database_url[0].id
  secret_data = local.ticketforge_async_database_url
}

resource "google_service_account" "ticketforge_api" {
  count        = var.enable_ticketforge_app_cloud_run ? 1 : 0
  account_id   = "ticketforge-api-sa"
  display_name = "TicketForge API Cloud Run"
}

resource "google_service_account" "ticketforge_inference" {
  count        = var.enable_ticketforge_app_cloud_run ? 1 : 0
  account_id   = "ticketforge-inference-sa"
  display_name = "TicketForge Inference Cloud Run"
}

resource "google_service_account" "ticketforge_web" {
  count        = var.enable_ticketforge_app_cloud_run ? 1 : 0
  account_id   = "ticketforge-web-sa"
  display_name = "TicketForge Web Cloud Run"
}

resource "google_project_iam_member" "ticketforge_api_cloudsql" {
  count   = var.enable_ticketforge_app_cloud_run ? 1 : 0
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.ticketforge_api[0].email}"
}

resource "google_secret_manager_secret_iam_member" "ticketforge_api_dburl_accessor" {
  count     = var.enable_ticketforge_app_cloud_run ? 1 : 0
  secret_id = google_secret_manager_secret.ticketforge_api_database_url[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ticketforge_api[0].email}"
}

resource "google_secret_manager_secret_iam_member" "ticketforge_api_jwt_accessor" {
  count     = var.enable_ticketforge_app_cloud_run ? 1 : 0
  secret_id = google_secret_manager_secret.ticketforge_api_jwt[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ticketforge_api[0].email}"
}

resource "google_cloud_run_v2_service" "ticketforge_api" {
  count               = var.enable_ticketforge_app_cloud_run ? 1 : 0
  name                = var.ticketforge_api_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.ticketforge_api[0].email
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.airflow_vpc.id
        subnetwork = google_compute_subnetwork.airflow_subnet.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.ticketforge_api_container_image
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            version = "latest"
            secret  = google_secret_manager_secret.ticketforge_api_database_url[0].secret_id
          }
        }
      }

      env {
        name = "JWT_SECRET_KEY"
        value_source {
          secret_key_ref {
            version = "latest"
            secret  = google_secret_manager_secret.ticketforge_api_jwt[0].secret_id
          }
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_version.ticketforge_api_database_url,
    google_secret_manager_secret_version.ticketforge_api_jwt,
  ]

  lifecycle {
    precondition {
      condition     = !var.enable_ticketforge_app_cloud_run || var.ticketforge_api_container_image != ""
      error_message = "ticketforge_api_container_image must be set when enable_ticketforge_app_cloud_run is true."
    }
  }
}

resource "google_cloud_run_v2_service" "ticketforge_inference" {
  count               = var.enable_ticketforge_app_cloud_run ? 1 : 0
  name                = var.ticketforge_inference_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account                  = google_service_account.ticketforge_inference[0].email
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.ticketforge_inference_container_image
      ports {
        container_port = 8080
      }
    }
  }

  lifecycle {
    precondition {
      condition     = !var.enable_ticketforge_app_cloud_run || var.ticketforge_inference_container_image != ""
      error_message = "ticketforge_inference_container_image must be set when enable_ticketforge_app_cloud_run is true."
    }
  }
}

resource "google_cloud_run_v2_service" "ticketforge_web" {
  count               = var.enable_ticketforge_app_cloud_run ? 1 : 0
  name                = var.ticketforge_web_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account                  = google_service_account.ticketforge_web[0].email
    max_instance_request_concurrency = 30

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.ticketforge_web_container_image
      ports {
        container_port = 8080
      }

    }
  }

  lifecycle {
    precondition {
      condition     = !var.enable_ticketforge_app_cloud_run || var.ticketforge_web_container_image != ""
      error_message = "ticketforge_web_container_image must be set when enable_ticketforge_app_cloud_run is true."
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "ticketforge_api_public_invoker" {
  count    = var.enable_ticketforge_app_cloud_run ? 1 : 0
  location = google_cloud_run_v2_service.ticketforge_api[0].location
  name     = google_cloud_run_v2_service.ticketforge_api[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "ticketforge_inference_public_invoker" {
  count    = var.enable_ticketforge_app_cloud_run ? 1 : 0
  location = google_cloud_run_v2_service.ticketforge_inference[0].location
  name     = google_cloud_run_v2_service.ticketforge_inference[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "ticketforge_web_public_invoker" {
  count    = var.enable_ticketforge_app_cloud_run ? 1 : 0
  location = google_cloud_run_v2_service.ticketforge_web[0].location
  name     = google_cloud_run_v2_service.ticketforge_web[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
