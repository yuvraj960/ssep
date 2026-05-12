resource "google_service_account" "ssep_services" {
  for_each = toset([
    "crowd-flow",
    "queue-predictor",
    "navigation",
    "order-deliver",
    "notification",
    "incident-manager",
    "gate-entry",
  ])

  account_id   = "ssep-${var.venue_id}-${each.value}"
  display_name = "SSEP ${each.value} service account"
  project      = var.project_id
}

resource "google_project_iam_member" "pubsub_publisher" {
  for_each = google_service_account.ssep_services

  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${each.value.email}"
}

resource "google_project_iam_member" "pubsub_subscriber" {
  for_each = google_service_account.ssep_services

  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${each.value.email}"
}

resource "google_project_iam_member" "firestore_user" {
  for_each = google_service_account.ssep_services

  project = var.project_id
  role    = "roles/firestore.user"
  member  = "serviceAccount:${each.value.email}"
}

resource "google_project_iam_member" "redis_user" {
  for_each = google_service_account.ssep_services

  project = var.project_id
  role    = "roles/redis.instanceUser"
  member  = "serviceAccount:${each.value.email}"
}

resource "google_project_iam_member" "logging_writer" {
  for_each = google_service_account.ssep_services

  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${each.value.email}"
}

resource "google_project_iam_member" "metric_writer" {
  for_each = google_service_account.ssep_services

  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${each.value.email}"
}

resource "google_project_iam_member" "trace_writer" {
  for_each = google_service_account.ssep_services

  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${each.value.email}"
}

output "service_account_emails" {
  value = { for k, sa in google_service_account.ssep_services : k => sa.email }
}
