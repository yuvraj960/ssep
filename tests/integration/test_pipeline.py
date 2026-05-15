import pytest
import httpx
import asyncio
import json

BASE_CROWD = "http://localhost:8080"
BASE_QUEUE = "http://localhost:8081"
BASE_NAV = "http://localhost:8082"
BASE_ORDER = "http://localhost:8083"
BASE_NOTIFY = "http://localhost:8084"
BASE_INCIDENT = "http://localhost:8085"
BASE_GATE = "http://localhost:8086"


@pytest.mark.asyncio
async def test_full_crowd_flow_pipeline():
    async with httpx.AsyncClient(timeout=10) as client:
        reading = {
            "sensor_id": "ble-int-001",
            "zone_id": "concourse-int-a",
            "sensor_type": "ble",
            "headcount": 200,
            "density": 0.72,
            "latitude": 40.0,
            "longitude": -74.0,
        }
        resp = await client.post(f"{BASE_CROWD}/api/v1/sensor-reading", json=reading)
        assert resp.status_code == 202

        heatmap = await client.get(f"{BASE_CROWD}/api/v1/heatmap")
        assert heatmap.status_code == 200
        data = heatmap.json()
        assert any(z["zone_id"] == "concourse-int-a" for z in data["zones"])


@pytest.mark.asyncio
async def test_queue_prediction_pipeline():
    async with httpx.AsyncClient(timeout=10) as client:
        observation = {
            "zone_id": "concourse-int-a",
            "facility_type": "concession",
            "facility_id": "conc-int-01",
            "queue_length": 30,
            "service_rate_per_min": 4.0,
            "minutes_since_event_start": 15,
            "is_halftime": False,
            "is_pre_game": False,
            "is_post_game": False,
            "day_of_week": 5,
            "attendance_pct": 0.80,
        }
        resp = await client.post(f"{BASE_QUEUE}/api/v1/predict", json=observation)
        assert resp.status_code == 200
        data = resp.json()
        assert data["estimated_wait_minutes"] >= 0
        assert data["facility_id"] == "conc-int-01"


@pytest.mark.asyncio
async def test_order_lifecycle():
    async with httpx.AsyncClient(timeout=10) as client:
        order = {
            "attendee_id": "int-att-001",
            "seat_section": "101",
            "seat_row": "C",
            "seat_number": "7",
            "items": [
                {"item_id": "burger", "name": "Burger", "quantity": 2, "unit_price": 9.0},
                {"item_id": "soda", "name": "Soda", "quantity": 2, "unit_price": 5.0},
            ],
        }
        create_resp = await client.post(f"{BASE_ORDER}/api/v1/orders", json=order)
        assert create_resp.status_code == 201
        order_id = create_resp.json()["order_id"]
        assert create_resp.json()["total_amount"] == 28.0

        get_resp = await client.get(f"{BASE_ORDER}/api/v1/orders/{order_id}")
        assert get_resp.status_code == 200

        status_resp = await client.patch(
            f"{BASE_ORDER}/api/v1/orders/{order_id}/status",
            json={"status": "preparing"},
        )
        assert status_resp.status_code == 200


@pytest.mark.asyncio
async def test_notification_and_incident():
    async with httpx.AsyncClient(timeout=10) as client:
        notif = {
            "target_type": "staff",
            "target_id": "int-staff-001",
            "channel": "dashboard",
            "title": "Integration Test Alert",
            "body": "Testing notification pipeline",
            "priority": "high",
        }
        notif_resp = await client.post(f"{BASE_NOTIFY}/api/v1/send", json=notif)
        assert notif_resp.status_code == 201
        assert notif_resp.json()["status"] == "sent"

        incident = {
            "category": "security",
            "severity": "high",
            "zone_id": "gate-int-a",
            "description": "Integration test incident",
            "reported_by": "int-staff-001",
        }
        inc_resp = await client.post(f"{BASE_INCIDENT}/api/v1/incidents", json=incident)
        assert inc_resp.status_code == 201
        incident_id = inc_resp.json()["incident_id"]
        assert inc_resp.json()["assigned_staff"] is not None

        update_resp = await client.patch(
            f"{BASE_INCIDENT}/api/v1/incidents/{incident_id}",
            json={"status": "acknowledged", "update_note": "Team responding"},
        )
        assert update_resp.status_code == 200


@pytest.mark.asyncio
async def test_gate_entry_tracking():
    async with httpx.AsyncClient(timeout=10) as client:
        for i in range(5):
            scan = {
                "gate_id": "gate-int-a",
                "ticket_id": f"int-tkt-{i:03d}",
                "scan_type": "entry",
            }
            resp = await client.post(f"{BASE_GATE}/api/v1/scan", json=scan)
            assert resp.status_code == 201

        status_resp = await client.get(f"{BASE_GATE}/api/v1/gates/gate-int-a")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["entry_count"] == 5
