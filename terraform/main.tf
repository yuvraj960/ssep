terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  backend "gcs" {
    bucket = "ssep-terraform-state"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "firestore.googleapis.com",
    "redis.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "cloudtrace.googleapis.com",
    "bigquery.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

module "pubsub" {
  source     = "../modules/pubsub"
  project_id = var.project_id
  venue_id   = var.venue_id
  depends_on = [google_project_service.apis]
}

module "firestore" {
  source     = "../modules/firestore"
  project_id = var.project_id
  venue_id   = var.venue_id
  region     = var.region
  depends_on = [google_project_service.apis]
}

module "redis" {
  source     = "../modules/redis"
  project_id = var.project_id
  region     = var.region
  venue_id   = var.venue_id
  tier       = var.redis_tier
  size_gb    = var.redis_size
  depends_on = [google_project_service.apis]
}

module "iam" {
  source     = "../modules/iam"
  project_id = var.project_id
  venue_id   = var.venue_id
  depends_on = [google_project_service.apis]
}

module "cloud_run" {
  source       = "../modules/cloud-run"
  project_id   = var.project_id
  region       = var.region
  venue_id     = var.venue_id
  environment  = var.environment
  min_instances = var.min_instances
  max_instances = var.max_instances
  redis_host   = module.redis.host
  pubsub_topics = module.pubsub.topic_ids
  depends_on = [
    google_project_service.apis,
    module.pubsub,
    module.redis,
    module.iam,
  ]
}

module "monitoring" {
  source     = "../../monitoring"
  project_id = var.project_id
  venue_id   = var.venue_id
  region     = var.region
  depends_on = [google_project_service.apis, module.cloud_run]
}

output "service_urls" {
  value = module.cloud_run.service_urls
}

output "redis_host" {
  value = module.redis.host
}

output "pubsub_topics" {
  value = module.pubsub.topic_names
}
