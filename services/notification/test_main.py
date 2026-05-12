import pytest
from fastapi.testclient import TestClient
from main import app, NOTIFICATION_LOG, STAFF_TASKS

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "notification"


def test_send_notification():
    NOTIFICATION_LOG.clear()
    payload = {
        "target_type": "attendee",
        "target_id": "att-001",
        "channel": "push",
        "title": "Gate Change",
        "body": "Gate A is less crowded. Consider Gate D.",
        "data": {"gate_id": "gate-d"},
        "priority": "normal",
    }
    response = client.post("/api/v1/send", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "sent"
    assert data["target_type"] == "attendee"


def test_assign_staff_task():
    STAFF_TASKS.clear()
    NOTIFICATION_LOG.clear()
    payload = {
        "staff_id": "staff-001",
        "task_type": "open_extra_lane",
        "zone_id": "gate-a",
        "description": "Open lane 3 at Gate A to reduce congestion",
        "priority": "high",
    }
    response = client.post("/api/v1/staff-task", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "assigned"
    assert data["staff_id"] == "staff-001"


def test_get_staff_tasks():
    response = client.get("/api/v1/staff-tasks/staff-001")
    assert response.status_code == 200
    data = response.json()
    assert data["total_tasks"] >= 1


def test_complete_task_not_found():
    response = client.patch("/api/v1/staff-tasks/nonexistent/complete")
    assert response.status_code == 404
