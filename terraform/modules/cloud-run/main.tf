variable "project_id" { type = string }
variable "region" { type = string }
variable "venue_id" { type = string }
variable "environment" { type = string }
variable "min_instances" { type = number }
variable "max_instances" { type = number }
variable "redis_host" { type = string }
variable "pubsub_topics" { type = map(string) }

locals {
  services = {
    crowd-flow = {
      image     = "${var.region}-docker.pkg.dev/${var.project_id}/ssep-images/crowd-flow:latest"
      port      = 8080
      memory    = "512Mi"
      cpu       = "2"
      timeout   = 60
      concurrency = 80
    }
    queue-predictor = {
      image     = "${var.region}-docker.pkg.dev/${var.project_id}/ssep-images/queue-predictor:latest"
      port      = 8081
      memory    = "1Gi"
      cpu       = "4"
      timeout   = 120
      concurrency = 40
    }
    navigation = {
      image     = "${var.region}-docker.pkg.dev/${var.project_id}/ssep-images/navigation:latest"
      port      = 8082
      memory    = "256Mi"
      cpu       = "2"
      timeout   = 30
      concurrency = 100
    }
    order-deliver = {
      image     = "${var.region}-docker.pkg.dev/${var.project_id}/ssep-images/order-deliver:latest"
      port      = 8083
      memory    = "512Mi"
      cpu       = "2"
      timeout   = 60
      concurrency = 80
    }
    notification = {
      image     = "${var.region}-docker.pkg.dev/${var.project_id}/ssep-images/notification:latest"
      port      = 8084
      memory    = "256Mi"
      cpu       = "1"
      timeout   = 30
      concurrency = 100
    }
    incident-manager = {
      image     = "${var.region}-docker.pkg.dev/${var.project_id}/ssep-images/incident-manager:latest"
      port      = 8085
      memory    = "256Mi"
      cpu       = "1"
      timeout   = 30
      concurrency = 80
    }
    gate-entry = {
      image     = "${var.region}-docker.pkg.dev/${var.project_id}/ssep-images/gate-entry:latest"
      port      = 8086
      memory    = "256Mi"
      cpu       = "2"
      timeout   = 30
      concurrency = 200
    }
  }
}

resource "google_cloud_run_v2_service" "ssep_services" {
  for_each = local.services

  name     = "${var.venue_id}-${replace(each.key, "-", "")}"
  project  = var.project_id
  location = var.region

  template {
    service_account = "ssep-${var.venue_id}-${each.key}@${var.project_id}.iam.gserviceaccount.com"

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = each.value.image
      ports {
        container_port = each.value.port
      }

      resources {
        limits = {
          memory = each.value.memory
          cpu    = each.value.cpu
        }
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "VENUE_ID"
        value = var.venue_id
      }

      env {
        name  = "REDIS_HOST"
        value = var.redis_host
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      volume_mounts {
        name       = "redis-cert"
        mount_path = "/etc/redis"
      }
    }

    timeout = "${each.value.timeout}s"

    vpc_access {
      connector = "projects/${var.project_id}/locations/${var.region}/connectors/ssep-vpc"
      egress    = "PRIVATE_RANGES_ONLY"
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  labels = {
    venue       = var.venue_id
    environment = var.environment
    service     = each.key
    platform    = "ssep"
  }
}

resource "google_cloud_run_v2_service_iam_binding" "public_invoker" {
  for_each = google_cloud_run_v2_service.ssep_services

  project  = var.project_id
  location = var.region
  name     = each.value.name
  role     = "roles/run.invoker"
  members  = ["allUsers"]
}

output "service_urls" {
  value = { for k, svc in google_cloud_run_v2_service.ssep_services : k => svc.uri }
}
