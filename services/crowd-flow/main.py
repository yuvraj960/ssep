import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared", "python-libs"))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any
import numpy as np
import asyncio
import logging

from ssep_common import PubSubClient, RedisClient, FirestoreClient, get_env, utc_now_iso, VENUE_TOPICS
from ssep_common.logging_config import setup_logging

logger = setup_logging("crowd-flow")

app = FastAPI(title="Crowd Flow Service", version="0.1.0")

pubsub: PubSubClient | None = None
redis_client: RedisClient | None = None
firestore_client: FirestoreClient | None = None
venue_id: str = ""


class SensorReading(BaseModel):
    sensor_id: str
    zone_id: str
    sensor_type: str = Field(..., pattern="^(ble|wifi|camera)$")
    headcount: int = Field(..., ge=0)
    density: float = Field(..., ge=0.0, le=1.0)
    latitude: float
    longitude: float
    timestamp: str | None = None


class ZoneDensity(BaseModel):
    zone_id: str
    density: float
    headcount: int
    congestion_level: str
    last_updated: str


class HeatMapResponse(BaseModel):
    venue_id: str
    zones: list[ZoneDensity]
    timestamp: str


ZONE_GRID: dict[str, dict[str, Any]] = {}

CONGESTION_THRESHOLDS = {
    "low": 0.0,
    "moderate": 0.35,
    "high": 0.65,
    "critical": 0.85,
}


def classify_congestion(density: float) -> str:
    if density >= CONGESTION_THRESHOLDS["critical"]:
        return "critical"
    if density >= CONGESTION_THRESHOLDS["high"]:
        return "high"
    if density >= CONGESTION_THRESHOLDS["moderate"]:
        return "moderate"
    return "low"


def compute_smoothed_density(zone_id: str, new_reading: SensorReading) -> float:
    existing = ZONE_GRID.get(zone_id, {})
    old_density = existing.get("density", 0.0)
    alpha = 0.3
    smoothed = alpha * new_reading.density + (1 - alpha) * old_density
    return round(smoothed, 4)


async def check_bottleneck(zone_id: str, density: float):
    if density >= CONGESTION_THRESHOLDS["critical"]:
        notification = {
            "venue_id": venue_id,
            "zone_id": zone_id,
            "alert_type": "bottleneck",
            "density": density,
            "congestion_level": "critical",
            "message": f"Critical congestion in zone {zone_id}. Auto-routing attendees.",
            "timestamp": utc_now_iso(),
        }
        pubsub.publish("notification.send", {
            "venue_id": venue_id,
            "notification_id": f"bottleneck-{zone_id}-{utc_now_iso()}",
            "target_type": "zone_attendees",
            "target_id": zone_id,
            "channel": "push",
            "title": "Congestion Alert",
            "body": f"Heavy congestion near {zone_id}. Consider alternate routes.",
            "data": {"alternate_route": True, "zone_id": zone_id},
            "event_time": utc_now_iso(),
        })
        logger.warning("bottleneck_detected", zone_id=zone_id, density=density)


@app.on_event("startup")
async def startup():
    global pubsub, redis_client, firestore_client, venue_id
    venue_id = get_env("VENUE_ID", "stadium-001")
    pubsub = PubSubClient()
    redis_client = RedisClient()
    await redis_client.connect()
    firestore_client = FirestoreClient.get_instance()
    logger.info("crowd_flow_started", venue_id=venue_id)


@app.on_event("shutdown")
async def shutdown():
    if redis_client:
        await redis_client.close()


@app.post("/api/v1/sensor-reading", status_code=202)
async def ingest_sensor_reading(reading: SensorReading):
    timestamp = reading.timestamp or utc_now_iso()
    smoothed_density = compute_smoothed_density(reading.zone_id, reading)

    zone_data = {
        "zone_id": reading.zone_id,
        "density": smoothed_density,
        "headcount": reading.headcount,
        "congestion_level": classify_congestion(smoothed_density),
        "latitude": reading.latitude,
        "longitude": reading.longitude,
        "sensor_type": reading.sensor_type,
        "last_updated": timestamp,
    }
    ZONE_GRID[reading.zone_id] = zone_data

    await redis_client.set_json(f"density:{venue_id}:{reading.zone_id}", zone_data, ex=300)

    event = {
        "venue_id": venue_id,
        "zone_id": reading.zone_id,
        "density": smoothed_density,
        "headcount": reading.headcount,
        "congestion_level": zone_data["congestion_level"],
        "event_time": timestamp,
    }
    pubsub.publish("crowd.density.updated", event)

    await check_bottleneck(reading.zone_id, smoothed_density)

    logger.info("sensor_ingested", zone_id=reading.zone_id, density=smoothed_density)
    return {"status": "accepted", "zone_id": reading.zone_id, "density": smoothed_density}


@app.post("/api/v1/sensor-readings/batch", status_code=202)
async def ingest_batch(readings: list[SensorReading]):
    results = []
    for reading in readings:
        result = await ingest_sensor_reading(reading)
        results.append(result)
    return {"status": "accepted", "count": len(results), "results": results}


@app.get("/api/v1/heatmap", response_model=HeatMapResponse)
async def get_heatmap():
    zones = []
    for zone_id, data in ZONE_GRID.items():
        zones.append(ZoneDensity(
            zone_id=zone_id,
            density=data["density"],
            headcount=data["headcount"],
            congestion_level=data["congestion_level"],
            last_updated=data["last_updated"],
        ))
    return HeatMapResponse(
        venue_id=venue_id,
        zones=zones,
        timestamp=utc_now_iso(),
    )


@app.get("/api/v1/zone/{zone_id}")
async def get_zone_density(zone_id: str):
    cached = await redis_client.get_json(f"density:{venue_id}:{zone_id}")
    if cached:
        return cached
    if zone_id in ZONE_GRID:
        return ZONE_GRID[zone_id]
    raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "crowd-flow", "zones_tracked": len(ZONE_GRID)}
