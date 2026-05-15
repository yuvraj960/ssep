variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "GCP region for Cloud Run"
}

variable "venue_id" {
  type        = string
  default     = "stadium-001"
  description = "Venue identifier for multi-stadium deployment"
}

variable "environment" {
  type        = string
  default     = "dev"
  description = "Environment (dev/staging/prod)"
}

variable "redis_tier" {
  type        = string
  default     = "BASIC"
  description = "Redis tier (BASIC for dev, STANDARD_HA for prod)"
}

variable "redis_size" {
  type        = number
  default     = 1
  description = "Redis instance size in GB"
}

variable "min_instances" {
  type        = number
  default     = 0
  description = "Minimum Cloud Run instances (0 for scale-to-zero)"
}

variable "max_instances" {
  type        = number
  default     = 100
  description = "Maximum Cloud Run instances per service"
}

variable "artifact_repo" {
  type        = string
  default     = "ssep-images"
  description = "Artifact Registry repository name"
}

locals {
  service_prefix = "ssep-${var.venue_id}"
  labels = {
    venue       = var.venue_id
    environment = var.environment
    platform    = "ssep"
    managed-by  = "terraform"
  }
}
