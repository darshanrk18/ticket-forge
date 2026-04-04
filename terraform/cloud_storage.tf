resource "google_storage_bucket" "training_artifacts" {
  name                        = local.effective_training_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }

    condition {
      age = 30
    }
  }
}

resource "google_storage_bucket_object" "training_index" {
  name         = "index.json"
  bucket       = google_storage_bucket.training_artifacts.name
  content_type = "application/json"
  content = jsonencode({
    current_dataset = "gs://${google_storage_bucket.training_artifacts.name}/datasets/v1.0/data.parquet"
    dataset_version = "v1.0"
    created_date    = "1970-01-01T00:00:00Z"
    description     = "Bootstrap index. Update before running cloud training."
  })
}
