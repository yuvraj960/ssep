import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared", "python-libs"))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any
from enum import Enum
import uuid
import asyncio

from ssep_common import PubSubClient, FirestoreClient, get_env, utc_now_iso
from ssep_common.logging_config import setup_logging

logger = setup_logging("notification")

app = FastAPI(title="Notification Service", version="0.1.0")

pubsub: PubSubClient | None = None
firestore_client: FirestoreClient | None = None
venue_id: str = ""


class Channel(str, Enum):
    PUSH = "push"
    SMS = "sms"
    SIGNAGE = "signage"
    DASHBOARD = "dashboard"


class TargetType(str, Enum):
    ATTENDEE = "attendee"
    ZONE_ATTENDEES = "zone_attendees"
    STAFF = "staff"
    ALL_STAFF = "all_staff"
    ALL_ATTENDEES = "all_attendees"


class SendNotificationRequest(BaseModel):
    target_type: TargetType
    target_id: str
    channel: Channel = Channel.PUSH
    title: str
    body: str
    data: dict[str, str] | None = None
    priority: str = Field("normal", pattern="^(normal|high|urgent)$")


class TaskAssignmentRequest(BaseModel):
    staff_id: str
    task_type: str
    zone_id: str
    description: str
    priority: str = Field("normal", pattern="^(normal|high|urgent)$")


class NotificationRecord(BaseModel):
    notification_id: str
    venue_id: str
    target_type: str
    target_id: str
    channel: str
    title: str
    body: str
    data: dict[str, str] | None
    priority: str
    status: str
    sent_at: str
    delivered_at: str | None = None


NOTIFICATION_LOG: list[dict[str, Any]] = []
STAFF_TASKS: dict[str, list[dict[str, Any]]] = {}


@app.on_event("startup")
async def startup():
    global pubsub, firestore_client, venue_id
    venue_id = get_env("VENUE_ID", "stadium-001")
    pubsub = PubSubClient()
    firestore_client = FirestoreClient.get_instance()
    logger.info("notification_service_started", venue_id=venue_id)


@app.post("/api/v1/send", response_model=NotificationRecord, status_code=201)
async def send_notification(request: SendNotificationRequest):
    notification_id = f"notif-{uuid.uuid4().hex[:12]}"
    now = utc_now_iso()

    record = {
        "notification_id": notification_id,
        "venue_id": venue_id,
        "target_type": request.target_type,
        "target_id": request.target_id,
        "channel": request.channel,
        "title": request.title,
        "body": request.body,
        "data": request.data or {},
        "priority": request.priority,
        "status": "sent",
        "sent_at": now,
        "delivered_at": now if request.channel in [Channel.SIGNAGE, Channel.DASHBOARD] else None,
    }

    NOTIFICATION_LOG.append(record)

    pubsub.publish("notification.send", {
        "venue_id": venue_id,
        "notification_id": notification_id,
        "target_type": request.target_type,
        "target_id": request.target_id,
        "channel": request.channel,
        "title": request.title,
        "body": request.body,
        "data": request.data or {},
        "event_time": now,
    })

    logger.info(
        "notification_sent",
        notification_id=notification_id,
        channel=request.channel,
        target_type=request.target_type,
        target_id=request.target_id,
    )

    return NotificationRecord(**record)


@app.post("/api/v1/staff-task", status_code=201)
async def assign_staff_task(request: TaskAssignmentRequest):
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    now = utc_now_iso()

    task = {
        "task_id": task_id,
        "venue_id": venue_id,
        "staff_id": request.staff_id,
        "task_type": request.task_type,
        "zone_id": request.zone_id,
        "description": request.description,
        "priority": request.priority,
        "status": "assigned",
        "assigned_at": now,
        "completed_at": None,
    }

    if request.staff_id not in STAFF_TASKS:
        STAFF_TASKS[request.staff_id] = []
    STAFF_TASKS[request.staff_id].append(task)

    await send_notification(SendNotificationRequest(
        target_type=TargetType.STAFF,
        target_id=request.staff_id,
        channel=Channel.DASHBOARD,
        title=f"New Task: {request.task_type}",
        body=request.description,
        data={"task_id": task_id, "zone_id": request.zone_id},
        priority=request.priority,
    ))

    logger.info("staff_task_assigned", task_id=task_id, staff_id=request.staff_id, zone=request.zone_id)
    return task


@app.get("/api/v1/staff-tasks/{staff_id}")
async def get_staff_tasks(staff_id: str):
    tasks = STAFF_TASKS.get(staff_id, [])
    active = [t for t in tasks if t["status"] != "completed"]
    return {
        "staff_id": staff_id,
        "active_tasks": active,
        "total_tasks": len(tasks),
        "active_count": len(active),
    }


@app.patch("/api/v1/staff-tasks/{task_id}/complete")
async def complete_staff_task(task_id: str):
    for staff_id, tasks in STAFF_TASKS.items():
        for task in tasks:
            if task["task_id"] == task_id:
                task["status"] = "completed"
                task["completed_at"] = utc_now_iso()
                logger.info("staff_task_completed", task_id=task_id, staff_id=staff_id)
                return {"task_id": task_id, "status": "completed"}
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@app.post("/api/v1/broadcast/zone")
async def broadcast_to_zone(zone_id: str, title: str, body: str, priority: str = "normal"):
    return await send_notification(SendNotificationRequest(
        target_type=TargetType.ZONE_ATTENDEES,
        target_id=zone_id,
        channel=Channel.PUSH,
        title=title,
        body=body,
        priority=priority,
    ))


@app.post("/api/v1/broadcast/all-staff")
async def broadcast_to_all_staff(title: str, body: str, priority: str = "high"):
    return await send_notification(SendNotificationRequest(
        target_type=TargetType.ALL_STAFF,
        target_id="all",
        channel=Channel.DASHBOARD,
        title=title,
        body=body,
        priority=priority,
    ))


@app.post("/api/v1/broadcast/signage")
async def update_digital_signage(zone_id: str, message: str, display_duration_seconds: int = 30):
    return await send_notification(SendNotificationRequest(
        target_type=TargetType.ZONE_ATTENDEES,
        target_id=zone_id,
        channel=Channel.SIGNAGE,
        title="Digital Signage Update",
        body=message,
        data={"display_duration_seconds": str(display_duration_seconds)},
    ))


@app.get("/api/v1/history")
async def get_notification_history(limit: int = 50, offset: int = 0):
    records = NOTIFICATION_LOG[offset:offset + limit]
    return {
        "notifications": records,
        "total": len(NOTIFICATION_LOG),
        "limit": limit,
        "offset": offset,
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "notification",
        "notifications_sent": len(NOTIFICATION_LOG),
    }
