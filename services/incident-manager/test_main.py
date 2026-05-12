import pytest
from fastapi.testclient import TestClient
from main import app, INCIDENTS

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "incident-manager"


def test_create_incident():
    INCIDENTS.clear()
    payload = {
        "category": "security",
        "severity": "high",
        "zone_id": "concourse-a",
        "description": "Unauthorized entry detected at Gate A",
        "reported_by": "staff-001",
    }
    response = client.post("/api/v1/incidents", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "open"
    assert data["assigned_staff"] is not None


def test_update_incident():
    INCIDENTS.clear()
    create_payload = {
        "category": "medical",
        "severity": "critical",
        "zone_id": "section-101",
        "description": "Attendee collapsed in Section 101",
        "reported_by": "staff-002",
    }
    create_resp = client.post("/api/v1/incidents", json=create_payload)
    incident_id = create_resp.json()["incident_id"]

    update_payload = {
        "status": "in_progress",
        "assigned_staff": "medic-team-lead",
        "update_note": "Medic team dispatched",
    }
    update_resp = client.patch(f"/api/v1/incidents/{incident_id}", json=update_payload)
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "in_progress"


def test_list_incidents():
    INCIDENTS.clear()
    client.post("/api/v1/incidents", json={
        "category": "maintenance", "severity": "low", "zone_id": "restroom-n",
        "description": "Sink broken", "reported_by": "staff-003",
    })
    response = client.get("/api/v1/incidents")
    assert response.status_code == 200
    assert response.json()["count"] >= 1


def test_dashboard_summary():
    INCIDENTS.clear()
    client.post("/api/v1/incidents", json={
        "category": "security", "severity": "high", "zone_id": "gate-a",
        "description": "Test", "reported_by": "staff-001",
    })
    response = client.get("/api/v1/incidents/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert "open_incidents" in data
