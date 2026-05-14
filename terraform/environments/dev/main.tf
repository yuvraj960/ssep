terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  backend "gcs" {
    bucket = "ssep-terraform-state-dev"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

module "infra" {
  source       = "../../"
  project_id   = var.project_id
  region       = var.region
  venue_id     = var.venue_id
  environment  = "dev"
  redis_tier   = "BASIC"
  redis_size   = 1
  min_instances = 0
  max_instances = 10
}
