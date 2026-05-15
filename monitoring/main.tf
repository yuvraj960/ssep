resource "google_monitoring_notification_channel" "ssep_pager" {
  project     = var.project_id
  display_name = "SSEP On-Call Pager - ${var.venue_id}"
  type         = "pubsub"
  labels = {
    topic = "${var.venue_id}-notification-send"
  }
}

resource "google_monitoring_alert_policy" "notification_p99_latency" {
  project     = var.project_id
  display_name = "SSEP Notification Service p99 Latency > 500ms"
  combiner     = "OR"

  conditions {
    condition_threshold {
      filter = <<-EOT
        resource.type = "cloud_run_revision"
        resource.labels.service_name = "${var.venue_id}-notification"
        metric.type = "run.googleapis.com/request_latencies"
      EOT

      threshold_value = 500
      comparison      = "COMPARISON_GT"
      duration        = "60s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_PERCENTILE_99"
      }
    }

    display_name = "Notification p99 latency exceeds 500ms"
  }

  notification_channels = [google_monitoring_notification_channel.ssep_pager.id]

  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "crowd_flow_refresh_rate" {
  project     = var.project_id
  display_name = "SSEP Crowd Flow Heat-Map Stale > 30s"
  combiner     = "OR"

  conditions {
    condition_threshold {
      filter = <<-EOT
        resource.type = "cloud_run_revision"
        resource.labels.service_name = "${var.venue_id}-crowdflow"
        metric.type = "run.googleapis.com/request_count"
      EOT

      threshold_value = 0
      comparison      = "COMPARISON_LT"
      duration        = "30s"

      aggregations {
        alignment_period   = "30s"
        per_series_aligner = "ALIGN_RATE"
      }
    }

    display_name = "No crowd flow updates in 30s during event"
  }

  notification_channels = [google_monitoring_notification_channel.ssep_pager.id]
}

resource "google_monitoring_alert_policy" "high_error_rate" {
  project     = var.project_id
  display_name = "SSEP Service Error Rate > 5%"
  combiner     = "OR"

  conditions {
    condition_threshold {
      filter = <<-EOT
        resource.type = "cloud_run_revision"
        metric.type = "run.googleapis.com/request_count"
        metric.labels.response_code_class = "5xx"
      EOT

      threshold_value = 0.05
      comparison      = "COMPARISON_GT"
      duration        = "120s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
        group_by_fields    = ["resource.labels.service_name"]
      }
    }

    display_name = "5xx error rate exceeds 5%"
  }

  notification_channels = [google_monitoring_notification_channel.ssep_pager.id]

  alert_strategy {
    auto_close = "3600s"
  }
}

resource "google_monitoring_alert_policy" "cloud_run_instance_exhaustion" {
  project     = var.project_id
  display_name = "SSEP Cloud Run Near Max Instances"
  combiner     = "OR"

  conditions {
    condition_threshold {
      filter = <<-EOT
        resource.type = "cloud_run_revision"
        metric.type = "run.googleapis.com/container/instance_count"
      EOT

      threshold_value = 80
      comparison      = "COMPARISON_GT"
      duration        = "120s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }

    display_name = "Service approaching max instance limit"
  }

  notification_channels = [google_monitoring_notification_channel.ssep_pager.id]
}

resource "google_monitoring_dashboard" "ssep_main" {
  project     = var.project_id
  dashboard_json = jsonencode({
    displayName = "SSEP - ${var.venue_id} Main Dashboard"
    mosaicLayout = {
      tiles = [
        {
          width  = 6
          height = 4
          widget = {
            title   = "Cloud Run Request Latency (p50, p95, p99)"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"cloud_run_revision\" metric.type=\"run.googleapis.com/request_latencies\""
                    aggregation = {
                      alignmentPeriod   = "60s"
                      perSeriesAligner  = "ALIGN_PERCENTILE_50"
                      groupByFields     = ["resource.labels.service_name"]
                    }
                  }
                }
              }]
            }
          }
        },
        {
          width  = 6
          height = 4
          widget = {
            title   = "Cloud Run Instance Count by Service"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"cloud_run_revision\" metric.type=\"run.googleapis.com/container/instance_count\""
                    aggregation = {
                      alignmentPeriod   = "60s"
                      perSeriesAligner  = "ALIGN_MEAN"
                      groupByFields     = ["resource.labels.service_name"]
                    }
                  }
                }
              }]
            }
          }
        },
        {
          width  = 6
          height = 4
          widget = {
            title   = "Pub/Sub Message Throughput"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"pubsub_topic\" metric.type=\"pubsub.googleapis.com/topic/send_message_operation_count\""
                    aggregation = {
                      alignmentPeriod   = "60s"
                      perSeriesAligner  = "ALIGN_RATE"
                      groupByFields     = ["resource.labels.topic_id"]
                    }
                  }
                }
              }]
            }
          }
        },
        {
          width  = 6
          height = 4
          widget = {
            title   = "5xx Error Rate by Service"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"cloud_run_revision\" metric.type=\"run.googleapis.com/request_count\" metric.labels.response_code_class=\"5xx\""
                    aggregation = {
                      alignmentPeriod   = "60s"
                      perSeriesAligner  = "ALIGN_RATE"
                      groupByFields     = ["resource.labels.service_name"]
                    }
                  }
                }
              }]
            }
          }
        },
      ]
    }
  })
}

output "dashboard_name" {
  value = google_monitoring_dashboard.ssep_main.id
}
