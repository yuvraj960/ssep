resource "google_redis_instance" "ssep_redis" {
  name           = "${var.venue_id}-redis"
  project        = var.project_id
  region         = var.region
  tier           = var.tier
  memory_size_gb = var.size_gb

  redis_version     = "REDIS_7_0"
  display_name      = "SSEP Redis - ${var.venue_id}"
  connect_mode     = "PRIVATE_SERVICE_ACCESS"

  labels = {
    venue    = var.venue_id
    platform = "ssep"
  }

  auth_enabled = true
}

output "host" {
  value       = google_redis_instance.ssep_redis.host
  description = "Redis instance host IP"
}

output "port" {
  value       = google_redis_instance.ssep_redis.port
  description = "Redis instance port"
}

output "id" {
  value = google_redis_instance.ssep_redis.id
}
