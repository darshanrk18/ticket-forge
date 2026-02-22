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
