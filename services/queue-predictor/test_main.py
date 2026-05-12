import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "queue-predictor"


def test_predict_wait_time():
    observation = {
        "zone_id": "concourse-a",
        "facility_type": "concession",
        "facility_id": "conc-a-01",
        "queue_length": 25,
        "service_rate_per_min": 3.0,
        "minutes_since_event_start": 30,
        "is_halftime": False,
        "is_pre_game": False,
        "is_post_game": False,
        "day_of_week": 5,
        "attendance_pct": 0.85,
    }
    response = client.post("/api/v1/predict", json=observation)
    assert response.status_code == 200
    data = response.json()
    assert data["estimated_wait_minutes"] >= 0
    assert data["facility_id"] == "conc-a-01"


def test_predict_halftime_surge():
    observation = {
        "zone_id": "concourse-b",
        "facility_type": "restroom",
        "facility_id": "rest-b-01",
        "queue_length": 40,
        "service_rate_per_min": 5.0,
        "minutes_since_event_start": 45,
        "is_halftime": True,
        "is_pre_game": False,
        "is_post_game": False,
        "day_of_week": 6,
        "attendance_pct": 0.95,
    }
    response = client.post("/api/v1/predict", json=observation)
    assert response.status_code == 200
    data = response.json()
    assert data["estimated_wait_minutes"] > 0
