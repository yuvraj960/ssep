resource "google_firestore_database" "ssep_firestore" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region

  type             = "FIRESTORE_NATIVE"
  deletion_policy  = "DELETE"

  depends_on = [google_project_service.firestore_api]
}

resource "google_project_service" "firestore_api" {
  service            = "firestore.googleapis.com"
  project            = var.project_id
  disable_on_destroy = false
}

resource "google_firestore_index" "orders_by_attendee" {
  project    = var.project_id
  database   = google_firestore_database.ssep_firestore.name
  collection = "orders"

  fields {
    field_path = "attendee_id"
    order      = "ASCENDING"
  }

  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "incidents_by_status" {
  project    = var.project_id
  database   = google_firestore_database.ssep_firestore.name
  collection = "incidents"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }

  fields {
    field_path = "severity"
    order      = "ASCENDING"
  }

  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "crowd_density_by_zone" {
  project    = var.project_id
  database   = google_firestore_database.ssep_firestore.name
  collection = "crowd_density"

  fields {
    field_path = "venue_id"
    order      = "ASCENDING"
  }

  fields {
    field_path = "zone_id"
    order      = "ASCENDING"
  }

  fields {
    field_path = "last_updated"
    order      = "DESCENDING"
  }
}

output "firestore_name" {
  value = google_firestore_database.ssep_firestore.name
}
