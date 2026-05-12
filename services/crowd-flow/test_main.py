import pytest
from fastapi.testclient import TestClient
from main import app, ZONE_GRID

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "crowd-flow"


def test_ingest_sensor_reading():
    ZONE_GRID.clear()
    reading = {
        "sensor_id": "ble-001",
        "zone_id": "concourse-a",
        "sensor_type": "ble",
        "headcount": 150,
        "density": 0.45,
        "latitude": 40.0,
        "longitude": -74.0,
    }
    response = client.post("/api/v1/sensor-reading", json=reading)
    assert response.status_code == 202
    data = response.json()
    assert data["zone_id"] == "concourse-a"


def test_get_heatmap():
    ZONE_GRID.clear()
    ZONE_GRID["test-zone"] = {
        "zone_id": "test-zone",
        "density": 0.5,
        "headcount": 100,
        "congestion_level": "moderate",
        "last_updated": "2026-01-01T00:00:00+00:00",
    }
    response = client.get("/api/v1/heatmap")
    assert response.status_code == 200
    data = response.json()
    assert len(data["zones"]) >= 1


def test_zone_not_found():
    ZONE_GRID.clear()
    response = client.get("/api/v1/zone/nonexistent")
    assert response.status_code == 404


def test_batch_ingest():
    ZONE_GRID.clear()
    readings = [
        {
            "sensor_id": "ble-001",
            "zone_id": "zone-a",
            "sensor_type": "ble",
            "headcount": 50,
            "density": 0.2,
            "latitude": 40.0,
            "longitude": -74.0,
        },
        {
            "sensor_id": "wifi-002",
            "zone_id": "zone-b",
            "sensor_type": "wifi",
            "headcount": 300,
            "density": 0.9,
            "latitude": 40.01,
            "longitude": -74.01,
        },
    ]
    response = client.post("/api/v1/sensor-readings/batch", json=readings)
    assert response.status_code == 202
    assert response.json()["count"] == 2
