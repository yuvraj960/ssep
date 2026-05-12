import pytest
from fastapi.testclient import TestClient
from main import app, GATE_STATS, RECENT_SCANS

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "gate-entry"


def test_process_scan():
    GATE_STATS.clear()
    RECENT_SCANS.clear()
    scan = {"gate_id": "gate-a", "ticket_id": "tkt-001", "scan_type": "entry"}
    response = client.post("/api/v1/scan", json=scan)
    assert response.status_code == 201
    data = response.json()
    assert data["gate_id"] == "gate-a"
    assert data["gate_status"] in ["idle", "low", "moderate", "high", "surge"]


def test_gate_status_not_found():
    GATE_STATS.clear()
    response = client.get("/api/v1/gates/nonexistent")
    assert response.status_code == 404


def test_list_gates():
    GATE_STATS.clear()
    RECENT_SCANS.clear()
    client.post("/api/v1/scan", json={"gate_id": "gate-x", "ticket_id": "tkt-100", "scan_type": "entry"})
    response = client.get("/api/v1/gates")
    assert response.status_code == 200
    assert response.json()["count"] >= 1
