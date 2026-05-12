import pytest
from fastapi.testclient import TestClient
from main import app, ORDERS, RUNNERS

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "order-deliver"


def test_get_menu():
    response = client.get("/api/v1/menu")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) > 0


def test_create_order():
    ORDERS.clear()
    order = {
        "attendee_id": "att-001",
        "seat_section": "101",
        "seat_row": "A",
        "seat_number": "12",
        "items": [
            {"item_id": "hot-dog", "name": "Hot Dog", "quantity": 2, "unit_price": 6.50},
            {"item_id": "beer", "name": "Draft Beer", "quantity": 1, "unit_price": 11.00},
        ],
    }
    response = client.post("/api/v1/orders", json=order)
    assert response.status_code == 201
    data = response.json()
    assert data["total_amount"] == 24.0
    assert data["status"] in ["pending", "confirmed"]


def test_create_order_invalid_item():
    order = {
        "attendee_id": "att-002",
        "seat_section": "201",
        "seat_row": "B",
        "seat_number": "5",
        "items": [{"item_id": "nonexistent", "name": "Fake", "quantity": 1, "unit_price": 1.0}],
    }
    response = client.post("/api/v1/orders", json=order)
    assert response.status_code == 400


def test_get_order_not_found():
    response = client.get("/api/v1/orders/nonexistent")
    assert response.status_code == 404
