resource "google_pubsub_topic" "ssep_topics" {
  for_each = toset([
    "crowd.density.updated",
    "queue.wait.changed",
    "gate.scan.event",
    "order.created",
    "order.status.changed",
    "incident.created",
    "incident.updated",
    "notification.send",
  ])

  name   = "${var.venue_id}-${replace(each.value, ".", "-")}"
  project = var.project_id

  message_retention_duration = "86400s"

  labels = {
    venue    = var.venue_id
    platform = "ssep"
  }
}

resource "google_pubsub_subscription" "crowd_flow_sub" {
  name    = "${var.venue_id}-crowd-flow-sub"
  topic   = google_pubsub_topic.ssep_topics["crowd.density.updated"].name
  project = var.project_id

  ack_deadline_seconds = 60

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  expiration_policy {
    ttl = ""
  }
}

resource "google_pubsub_subscription" "queue_predictor_sub" {
  name    = "${var.venue_id}-queue-predictor-sub"
  topic   = google_pubsub_topic.ssep_topics["queue.wait.changed"].name
  project = var.project_id

  ack_deadline_seconds = 60

  expiration_policy {
    ttl = ""
  }
}

resource "google_pubsub_subscription" "notification_sub" {
  name    = "${var.venue_id}-notification-sub"
  topic   = google_pubsub_topic.ssep_topics["notification.send"].name
  project = var.project_id

  ack_deadline_seconds = 30

  push_config {
    push_endpoint = ""
  }

  expiration_policy {
    ttl = ""
  }
}

resource "google_pubsub_subscription" "incident_sub" {
  name    = "${var.venue_id}-incident-sub"
  topic   = google_pubsub_topic.ssep_topics["incident.created"].name
  project = var.project_id

  ack_deadline_seconds = 60

  expiration_policy {
    ttl = ""
  }
}

output "topic_ids" {
  value = { for k, t in google_pubsub_topic.ssep_topics : k => t.id }
}

output "topic_names" {
  value = { for k, t in google_pubsub_topic.ssep_topics : k => t.name }
}
