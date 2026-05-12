import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared", "python-libs"))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any
from enum import Enum
import uuid

from ssep_common import PubSubClient, RedisClient, FirestoreClient, get_env, utc_now_iso
from ssep_common.logging_config import setup_logging

logger = setup_logging("order-deliver")

app = FastAPI(title="Order & Deliver Service", version="0.1.0")

pubsub: PubSubClient | None = None
redis_client: RedisClient | None = None
firestore_client: FirestoreClient | None = None
venue_id: str = ""


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    READY = "ready"
    PICKED_UP = "picked_up"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderItem(BaseModel):
    item_id: str
    name: str
    quantity: int = Field(..., ge=1)
    unit_price: float = Field(..., ge=0.0)


class CreateOrderRequest(BaseModel):
    attendee_id: str
    seat_section: str
    seat_row: str
    seat_number: str
    items: list[OrderItem] = Field(..., min_length=1)


class OrderResponse(BaseModel):
    order_id: str
    venue_id: str
    attendee_id: str
    seat_section: str
    seat_row: str
    seat_number: str
    items: list[OrderItem]
    total_amount: float
    status: OrderStatus
    assigned_runner: str | None = None
    estimated_delivery_minutes: float | None = None
    created_at: str
    updated_at: str


MENU: dict[str, dict[str, Any]] = {
    "hot-dog": {"name": "Hot Dog", "price": 6.50, "category": "food", "prep_minutes": 3},
    "burger": {"name": "Burger", "price": 9.00, "category": "food", "prep_minutes": 5},
    "nachos": {"name": "Nachos", "price": 7.50, "category": "food", "prep_minutes": 2},
    "beer": {"name": "Draft Beer", "price": 11.00, "category": "drink", "prep_minutes": 1},
    "soda": {"name": "Soda", "price": 5.00, "category": "drink", "prep_minutes": 1},
    "water": {"name": "Water Bottle", "price": 3.00, "category": "drink", "prep_minutes": 1},
    "popcorn": {"name": "Popcorn", "price": 6.00, "category": "food", "prep_minutes": 2},
    "pretzel": {"name": "Soft Pretzel", "price": 5.50, "category": "food", "prep_minutes": 2},
}

ORDERS: dict[str, dict[str, Any]] = {}
RUNNERS: list[dict[str, Any]] = []


def estimate_delivery(order: dict[str, Any]) -> float:
    max_prep = max(
        MENU.get(item["item_id"], {}).get("prep_minutes", 5)
        for item in order["items"]
    )
    walk_time = 4.0
    return max_prep + walk_time


def assign_runner() -> str | None:
    for runner in RUNNERS:
        if runner.get("active_orders", 0) < 3:
            runner["active_orders"] = runner.get("active_orders", 0) + 1
            return runner["runner_id"]
    return None


@app.on_event("startup")
async def startup():
    global pubsub, redis_client, firestore_client, venue_id
    venue_id = get_env("VENUE_ID", "stadium-001")
    pubsub = PubSubClient()
    redis_client = RedisClient()
    await redis_client.connect()
    firestore_client = FirestoreClient.get_instance()

    RUNNERS.extend([
        {"runner_id": f"runner-{i}", "name": f"Runner {i}", "zone": "concourse-a", "active_orders": 0}
        for i in range(1, 11)
    ])
    logger.info("order_deliver_started", venue_id=venue_id, runners=len(RUNNERS))


@app.on_event("shutdown")
async def shutdown():
    if redis_client:
        await redis_client.close()


@app.get("/api/v1/menu")
async def get_menu():
    items = []
    for item_id, details in MENU.items():
        items.append({"item_id": item_id, **details})
    return {"venue_id": venue_id, "items": items}


@app.post("/api/v1/orders", response_model=OrderResponse, status_code=201)
async def create_order(request: CreateOrderRequest):
    order_id = f"ord-{uuid.uuid4().hex[:12]}"
    now = utc_now_iso()

    validated_items = []
    total = 0.0
    for item in request.items:
        if item.item_id not in MENU:
            raise HTTPException(status_code=400, detail=f"Item {item.item_id} not on menu")
        menu_item = MENU[item.item_id]
        validated_items.append({
            "item_id": item.item_id,
            "name": menu_item["name"],
            "quantity": item.quantity,
            "unit_price": menu_item["price"],
        })
        total += menu_item["price"] * item.quantity

    runner_id = assign_runner()

    order = {
        "order_id": order_id,
        "venue_id": venue_id,
        "attendee_id": request.attendee_id,
        "seat_section": request.seat_section,
        "seat_row": request.seat_row,
        "seat_number": request.seat_number,
        "items": validated_items,
        "total_amount": round(total, 2),
        "status": OrderStatus.PENDING,
        "assigned_runner": runner_id,
        "estimated_delivery_minutes": None,
        "created_at": now,
        "updated_at": now,
    }

    if runner_id:
        order["status"] = OrderStatus.CONFIRMED
        order["estimated_delivery_minutes"] = estimate_delivery(order)

    ORDERS[order_id] = order

    await redis_client.set_json(f"order:{venue_id}:{order_id}", order, ex=3600)

    pubsub.publish("order.created", {
        "venue_id": venue_id,
        "order_id": order_id,
        "attendee_id": request.attendee_id,
        "seat_section": request.seat_section,
        "seat_row": request.seat_row,
        "seat_number": request.seat_number,
        "items": validated_items,
        "total_amount": order["total_amount"],
        "event_time": now,
    })

    logger.info("order_created", order_id=order_id, total=total, runner=runner_id)

    return OrderResponse(**order)


@app.get("/api/v1/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str):
    cached = await redis_client.get_json(f"order:{venue_id}:{order_id}")
    if cached:
        return OrderResponse(**cached)
    if order_id in ORDERS:
        return OrderResponse(**ORDERS[order_id])
    raise HTTPException(status_code=404, detail="Order not found")


@app.patch("/api/v1/orders/{order_id}/status")
async def update_order_status(order_id: str, status: OrderStatus):
    if order_id not in ORDERS:
        cached = await redis_client.get_json(f"order:{venue_id}:{order_id}")
        if cached:
            ORDERS[order_id] = cached
        else:
            raise HTTPException(status_code=404, detail="Order not found")

    order = ORDERS[order_id]
    valid_transitions = {
        OrderStatus.PENDING: [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
        OrderStatus.CONFIRMED: [OrderStatus.PREPARING, OrderStatus.CANCELLED],
        OrderStatus.PREPARING: [OrderStatus.READY, OrderStatus.CANCELLED],
        OrderStatus.READY: [OrderStatus.PICKED_UP, OrderStatus.CANCELLED],
        OrderStatus.PICKED_UP: [OrderStatus.DELIVERED],
    }

    current = OrderStatus(order["status"])
    allowed = valid_transitions.get(current, [])
    if status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {current} to {status}. Allowed: {[s.value for s in allowed]}",
        )

    order["status"] = status
    order["updated_at"] = utc_now_iso()

    if status == OrderStatus.DELIVERED and order.get("assigned_runner"):
        for runner in RUNNERS:
            if runner["runner_id"] == order["assigned_runner"]:
                runner["active_orders"] = max(0, runner.get("active_orders", 0) - 1)
                break

    await redis_client.set_json(f"order:{venue_id}:{order_id}", order, ex=3600)

    pubsub.publish("order.status.changed", {
        "venue_id": venue_id,
        "order_id": order_id,
        "status": status,
        "assigned_runner": order.get("assigned_runner"),
        "event_time": order["updated_at"],
    })

    logger.info("order_status_updated", order_id=order_id, status=status)
    return {"order_id": order_id, "status": status}


@app.get("/api/v1/orders/attendee/{attendee_id}")
async def get_attendee_orders(attendee_id: str):
    results = []
    for order in ORDERS.values():
        if order.get("attendee_id") == attendee_id:
            results.append(order)
    return {"attendee_id": attendee_id, "orders": results, "count": len(results)}


@app.get("/api/v1/runners")
async def list_runners():
    return {"runners": RUNNERS, "total": len(RUNNERS)}


@app.get("/health")
async def health():
    active_orders = sum(1 for o in ORDERS.values() if o["status"] not in [OrderStatus.DELIVERED, OrderStatus.CANCELLED])
    return {
        "status": "healthy",
        "service": "order-deliver",
        "active_orders": active_orders,
        "available_runners": sum(1 for r in RUNNERS if r.get("active_orders", 0) < 3),
    }
