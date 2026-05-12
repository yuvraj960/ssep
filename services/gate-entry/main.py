import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared", "python-libs"))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import uuid

from ssep_common import PubSubClient, RedisClient, FirestoreClient, get_env, utc_now_iso
from ssep_common.logging_config import setup_logging

logger = setup_logging("gate-entry")

app = FastAPI(title="Gate Entry Service", version="0.1.0")

pubsub: PubSubClient | None = None
redis_client: RedisClient | None = None
firestore_client: FirestoreClient | None = None
venue_id: str = ""


class GateScanRequest(BaseModel):
    gate_id: str
    ticket_id: str
    scan_type: str = Field("entry", pattern="^(entry|exit|reentry)$")


class GateStatusResponse(BaseModel):
    gate_id: str
    total_scans: int
    entry_count: int
    exit_count: int
    scans_per_minute: float
    avg_scan_interval_seconds: float
    status: str
    last_scan_at: str | None


GATE_STATS: dict[str, dict[str, Any]] = {}
RECENT_SCANS: dict[str, list[datetime]] = defaultdict(list)
VELOCITY_WINDOW_MINUTES = 5


def compute_velocity(gate_id: str) -> float:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=VELOCITY_WINDOW_MINUTES)
    RECENT_SCANS[gate_id] = [t for t in RECENT_SCANS[gate_id] if t > cutoff]
    if not RECENT_SCANS[gate_id]:
        return 0.0
    return round(len(RECENT_SCANS[gate_id]) / VELOCITY_WINDOW_MINUTES, 2)


def compute_avg_interval(gate_id: str) -> float:
    scans = sorted(RECENT_SCANS.get(gate_id, []))
    if len(scans) < 2:
        return 0.0
    intervals = [(scans[i + 1] - scans[i]).total_seconds() for i in range(len(scans) - 1)]
    return round(sum(intervals) / len(intervals), 2)


def classify_gate_status(velocity: float) -> str:
    if velocity > 80:
        return "surge"
    if velocity > 50:
        return "high"
    if velocity > 20:
        return "moderate"
    if velocity > 5:
        return "low"
    return "idle"


@app.on_event("startup")
async def startup():
    global pubsub, redis_client, firestore_client, venue_id
    venue_id = get_env("VENUE_ID", "stadium-001")
    pubsub = PubSubClient()
    redis_client = RedisClient()
    await redis_client.connect()
    firestore_client = FirestoreClient.get_instance()
    logger.info("gate_entry_started", venue_id=venue_id)


@app.on_event("shutdown")
async def shutdown():
    if redis_client:
        await redis_client.close()


@app.post("/api/v1/scan", status_code=201)
async def process_scan(request: GateScanRequest):
    now = datetime.now(timezone.utc)

    if request.gate_id not in GATE_STATS:
        GATE_STATS[request.gate_id] = {
            "gate_id": request.gate_id,
            "total_scans": 0,
            "entry_count": 0,
            "exit_count": 0,
            "last_scan_at": None,
        }

    stats = GATE_STATS[request.gate_id]
    stats["total_scans"] += 1
    stats["last_scan_at"] = utc_now_iso()

    if request.scan_type in ["entry", "reentry"]:
        stats["entry_count"] += 1
    else:
        stats["exit_count"] += 1

    RECENT_SCANS[request.gate_id].append(now)

    velocity = compute_velocity(request.gate_id)
    avg_interval = compute_avg_interval(request.gate_id)
    gate_status = classify_gate_status(velocity)

    event = {
        "venue_id": venue_id,
        "gate_id": request.gate_id,
        "ticket_id": request.ticket_id,
        "scan_type": request.scan_type,
        "scan_velocity_per_min": velocity,
        "gate_status": gate_status,
        "event_time": utc_now_iso(),
    }

    pubsub.publish("gate.scan.event", event)

    await redis_client.set_json(f"gate:{venue_id}:{request.gate_id}", {
        **stats,
        "scans_per_minute": velocity,
        "avg_scan_interval_seconds": avg_interval,
        "status": gate_status,
    }, ex=600)

    if gate_status == "surge":
        pubsub.publish("notification.send", {
            "venue_id": venue_id,
            "notification_id": f"gate-surge-{request.gate_id}-{utc_now_iso()}",
            "target_type": "all_staff",
            "target_id": "all",
            "channel": "dashboard",
            "title": f"Gate {request.gate_id} Surge",
            "body": f"Entry velocity at {velocity}/min. Consider opening additional lanes.",
            "data": {"gate_id": request.gate_id, "velocity": str(velocity)},
            "event_time": utc_now_iso(),
        })
        logger.warning("gate_surge", gate_id=request.gate_id, velocity=velocity)

    logger.info("scan_processed", gate_id=request.gate_id, scan_type=request.scan_type, velocity=velocity)
    return {
        "scan_id": f"scan-{uuid.uuid4().hex[:8]}",
        "gate_id": request.gate_id,
        "ticket_id": request.ticket_id,
        "scan_type": request.scan_type,
        "velocity": velocity,
        "gate_status": gate_status,
    }


@app.get("/api/v1/gates/{gate_id}", response_model=GateStatusResponse)
async def get_gate_status(gate_id: str):
    cached = await redis_client.get_json(f"gate:{venue_id}:{gate_id}")
    if cached:
        return GateStatusResponse(**cached)
    if gate_id in GATE_STATS:
        velocity = compute_velocity(gate_id)
        stats = GATE_STATS[gate_id]
        return GateStatusResponse(
            gate_id=gate_id,
            total_scans=stats["total_scans"],
            entry_count=stats["entry_count"],
            exit_count=stats["exit_count"],
            scans_per_minute=velocity,
            avg_scan_interval_seconds=compute_avg_interval(gate_id),
            status=classify_gate_status(velocity),
            last_scan_at=stats["last_scan_at"],
        )
    raise HTTPException(status_code=404, detail=f"Gate {gate_id} not found")


@app.get("/api/v1/gates")
async def list_gates():
    results = []
    for gate_id, stats in GATE_STATS.items():
        velocity = compute_velocity(gate_id)
        results.append({
            "gate_id": gate_id,
            "total_scans": stats["total_scans"],
            "entry_count": stats["entry_count"],
            "exit_count": stats["exit_count"],
            "scans_per_minute": velocity,
            "status": classify_gate_status(velocity),
            "last_scan_at": stats["last_scan_at"],
        })
    return {"venue_id": venue_id, "gates": results, "count": len(results)}


@app.get("/api/v1/gates/best-entry")
async def best_entry_gate():
    best_gate = None
    best_velocity = float("inf")

    for gate_id in GATE_STATS:
        velocity = compute_velocity(gate_id)
        if velocity < best_velocity:
            best_velocity = velocity
            best_gate = gate_id

    if best_gate:
        velocity = compute_velocity(best_gate)
        return {
            "gate_id": best_gate,
            "scans_per_minute": velocity,
            "status": classify_gate_status(velocity),
            "recommendation": "Use this gate for shortest wait" if velocity < 50 else "All gates busy",
        }
    return {"recommendation": "No gate data available yet"}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "gate-entry",
        "gates_tracked": len(GATE_STATS),
    }
