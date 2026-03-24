variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for resources."
  type        = string
  default     = "us-east1"
}

variable "state_bucket" {
  description = "Name for the tfstate bucket (must be globally unique)."
  type        = string
}

variable "data_bucket" {
  description = "Name for the data bucket (must be globally unique)."
  type        = string
  default     = "ticketforge-dvc"
}

variable "repository" {
  description = "the github repository in format 'ORGANIZATION/REPO'"
  type        = string
  default     = "ALearningCurve/ticket-forge"
}

variable "repository_id" {
  description = "the github repository in id format"
  type        = string
  default     = "1142699076"
}

variable "mlflow_service_name" {
  description = "Cloud Run service name for MLflow tracking server."
  type        = string
  default     = "mlflow-tracking"
}

variable "mlflow_server_image" {
  description = "Optional explicit container image for MLflow server. If null, Terraform uses Artifact Registry path <region>-docker.pkg.dev/<project>/mlflow-repo/mlflow-gcp:<tag>."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = var.mlflow_server_image == null || can(
      regex(
        "^(((?:[a-z0-9-]+\\.)?gcr\\.io)|(?:[a-z0-9-]+-docker\\.pkg\\.dev)|docker\\.io)/",
        var.mlflow_server_image,
      )
    )
    error_message = "mlflow_server_image must be null or use one of: docker.io, [region.]gcr.io, or [region-]docker.pkg.dev."
  }
}

variable "mlflow_artifact_registry_repository" {
  description = "Artifact Registry Docker repository name for the MLflow image."
  type        = string
  default     = "mlflow-repo"
}

variable "mlflow_image_tag" {
  description = "MLflow image tag used when mlflow_server_image is null."
  type        = string
  default     = "v3.10.0"

  validation {
    condition = can(
      regex("^[A-Za-z0-9._-]+$", var.mlflow_image_tag)
    )
    error_message = "mlflow_image_tag may only contain letters, numbers, dot, underscore, and dash."
  }
}

variable "mlflow_db_name" {
  description = "Cloud SQL database name used by MLflow backend store."
  type        = string
  default     = "mlflow"
}

variable "mlflow_db_user" {
  description = "Cloud SQL username used by MLflow backend store."
  type        = string
  default     = "mlflow"
}

variable "mlflow_db_tier" {
  description = "Cloud SQL machine tier for MLflow backend store."
  type        = string
  default     = "db-custom-1-3840"
}

variable "mlflow_additional_invokers" {
  description = "Extra Cloud Run invoker members for MLflow (e.g. user:you@example.com)."
  type        = list(string)
  default     = []
}
