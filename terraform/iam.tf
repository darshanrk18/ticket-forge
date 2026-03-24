/****************************************
The following defines the
IAM permissions and group
we use for the github actions.

There are two keys:
  1. the "read" key for planning
  2. the "write" key for applying
****************************************/

# 1. setup identity pool
resource "google_iam_workload_identity_pool" "github_pool" {
  workload_identity_pool_id = "github-actions-pool"
}

resource "google_iam_workload_identity_pool_provider" "github_provider" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
    "attribute.workflow"   = "assertion.workflow"
  }
  attribute_condition = <<EOT
  attribute.repository == "${var.repository}" &&
  assertion.repository_id == "${var.repository_id}"
  EOT

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# 2. create the accounts
resource "google_service_account" "tf_plan" {
  account_id   = "tf-plan-sa"
  display_name = "Terraform Planning Account"
}

resource "google_service_account" "tf_apply" {
  account_id   = "tf-apply-sa"
  display_name = "Terraform Apply Account"
}

resource "google_service_account" "ml_pipeline" {
  account_id   = "ml-pipeline-sa"
  display_name = "ML Pipeline Account"
  description  = "Used by model-cicd workflow: reads/writes DVC bucket, accesses Postgres and secrets."
}

# 3. allow github to impersonate
resource "google_service_account_iam_member" "tf_plan_impersonation" {
  service_account_id = google_service_account.tf_plan.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.repository}"
}

resource "google_service_account_iam_member" "tf_apply_impersonation" {
  service_account_id = google_service_account.tf_apply.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.repository}"
}

resource "google_service_account_iam_member" "ml_pipeline_impersonation" {
  service_account_id = google_service_account.ml_pipeline.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.repository}"
}

# 4. define and attach the permissions
locals {
  # READ-ONLY: Roles for the Planning Service Account
  plan_roles = [
    "roles/viewer",               # Generic read access to most resources
    "roles/iam.securityReviewer", # View IAM policies (critical for diffing IAM)
    "roles/storage.objectViewer", # View GCS objects (if using data sources)
    "roles/container.viewer",     # Specific view access for GKE
    "roles/run.viewer"            # Specific view access for Cloud Run
  ]

  # WRITE/ADMIN: Roles for the Apply Service Account
  apply_roles = [
    "roles/compute.admin",                   # Manage VM instances, Disks, Networks
    "roles/container.admin",                 # Manage GKE Clusters
    "roles/run.admin",                       # Manage Cloud Run Services
    "roles/storage.admin",                   # Manage GCS Buckets
    "roles/iam.serviceAccountUser",          # REQUIRED: To attach Service Accounts to Compute/Cloud Run
    "roles/iam.securityReviewer",            # View IAM policies
    "roles/iam.workloadIdentityPoolAdmin",   # REQUIRED: To manage workload identity pools (includes iam.workloadIdentityPools.get)
    "roles/resourcemanager.projectIamAdmin", # REQUIRED: To manage IAM bindings on the project
    "roles/serviceusage.serviceUsageAdmin"   # Enable APIs (google_project_service)
  ]

  # MINIMAL: Roles for the ML Pipeline Service Account
  ml_pipeline_roles = [
    "roles/cloudsql.client",              # Connect to Postgres (Cloud SQL)
    "roles/secretmanager.secretAccessor", # Read secrets (e.g. DB password)
  ]
}

resource "google_project_iam_member" "tf_plan_permissions" {
  for_each = toset(local.plan_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.tf_plan.email}"
}

resource "google_project_iam_member" "tf_apply_permissions" {
  for_each = toset(local.apply_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.tf_apply.email}"
}

resource "google_project_iam_member" "ml_pipeline_permissions" {
  for_each = toset(local.ml_pipeline_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.ml_pipeline.email}"
}

resource "google_storage_bucket_iam_member" "tf_plan_state_access" {
  bucket = var.state_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.tf_plan.email}"
}

resource "google_storage_bucket_iam_member" "tf_apply_state_access" {
  bucket = var.state_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.tf_apply.email}"
}

# ML pipeline needs read/write on the DVC data bucket
resource "google_storage_bucket_iam_member" "ml_pipeline_dvc_access" {
  bucket = var.data_bucket
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.ml_pipeline.email}"
}
