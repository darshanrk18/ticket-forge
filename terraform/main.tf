locals {
  airflow_vm_name = "airflow-vm-${var.environment}"
  effective_training_bucket = coalesce(
    var.training_bucket_name,
    "ticket-forge-training-artifacts-${var.project_id}-${var.environment}",
  )
}

resource "google_project_service" "airflow_services" {
  for_each = toset([
    "compute.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "artifactregistry.googleapis.com",
    "servicenetworking.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "state_bucket" {
  count                       = var.enable_terraform_state_bucket ? 1 : 0
  name                        = var.state_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket" "data_bucket" {
  name                        = var.data_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = false
  }

  lifecycle {
    prevent_destroy = true
  }
}


resource "google_compute_instance" "airflow_vm" {
  name         = local.airflow_vm_name
  machine_type = var.airflow_vm_machine_type
  zone         = var.zone
  tags         = ["airflow", "airflow-web"]

  boot_disk {
    initialize_params {
      image = "projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts"
      size  = var.airflow_vm_disk_size_gb
      type  = "pd-ssd"
    }
  }

  # VM is private; accessed only via IAP and Cloud NAT
  network_interface {
    network    = google_compute_network.airflow_vpc.id
    subnetwork = google_compute_subnetwork.airflow_subnet.id
  }

  service_account {
    email  = google_service_account.airflow_runtime.email
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = templatefile("${path.module}/templates/airflow_startup.sh.tftpl", {
    repository                             = var.repository
    repository_ref                         = var.airflow_repo_ref
    airflow_version                        = var.airflow_version
    airflow_username                       = var.airflow_admin_username
    airflow_password                       = local.airflow_admin_password
    db_connection                          = local.airflow_sqlalchemy_conn
    app_db_connection                      = local.ticketforge_sqlalchemy_conn
    dags_folder                            = "/opt/ticket-forge/dags"
    gcs_bucket                             = google_storage_bucket.training_artifacts.name
    gcp_region                             = var.region
    gcp_project                            = var.project_id
    github_token_secret_id                 = var.airflow_github_token_secret_id
    gmail_app_username_secret_id           = var.airflow_gmail_app_username_secret_id
    gmail_app_password_secret_id           = var.airflow_gmail_app_password_secret_id
    airflow_webserver_secret_key_secret_id = var.airflow_webserver_secret_key_secret_id
  })

  allow_stopping_for_update = true

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
  }

  depends_on = [
    google_project_service.airflow_services,
    google_sql_database.airflow,
    google_storage_bucket.training_artifacts,
    google_secret_manager_secret_version.airflow_webserver_secret_key,
  ]
}
