import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared", "python-libs"))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any
from enum import Enum
import uuid

from ssep_common import PubSubClient, FirestoreClient, get_env, utc_now_iso
from ssep_common.logging_config import setup_logging

logger = setup_logging("incident-manager")

app = FastAPI(title="Incident Manager Service", version="0.1.0")

pubsub: PubSubClient | None = None
firestore_client: FirestoreClient | None = None
venue_id: str = ""


class IncidentCategory(str, Enum):
    MEDICAL = "medical"
    SECURITY = "security"
    MAINTENANCE = "maintenance"
    CROWD_ISSUE = "crowd_issue"
    FACILITY = "facility"
    OTHER = "other"


class IncidentSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class CreateIncidentRequest(BaseModel):
    category: IncidentCategory
    severity: IncidentSeverity
    zone_id: str
    description: str
    reported_by: str


class UpdateIncidentRequest(BaseModel):
    status: IncidentStatus
    assigned_staff: str | None = None
    update_note: str | None = None


class IncidentResponse(BaseModel):
    incident_id: str
    venue_id: str
    category: str
    severity: str
    status: str
    zone_id: str
    description: str
    reported_by: str
    assigned_staff: str | None
    updates: list[dict[str, Any]]
    created_at: str
    updated_at: str


INCIDENTS: dict[str, dict[str, Any]] = {}

SEVERITY_PRIORITY = {
    IncidentSeverity.CRITICAL: 1,
    IncidentSeverity.HIGH: 2,
    IncidentSeverity.MEDIUM: 3,
    IncidentSeverity.LOW: 4,
}

AUTO_ASSIGNMENT_RULES: dict[str, list[str]] = {
    "medical": ["medic-team-lead", "medic-on-call"],
    "security": ["security-lead", "security-patrol"],
    "crowd_issue": ["crowd-control-lead", "operations-manager"],
    "maintenance": ["facilities-team", "maintenance-on-call"],
    "facility": ["facilities-team"],
    "other": ["operations-manager"],
}


def auto_assign_staff(category: str, severity: str) -> str | None:
    staff_list = AUTO_ASSIGNMENT_RULES.get(category, [])
    if severity in [IncidentSeverity.CRITICAL, IncidentSeverity.HIGH] and staff_list:
        return staff_list[0]
    if staff_list:
        return staff_list[-1]
    return None


@app.on_event("startup")
async def startup():
    global pubsub, firestore_client, venue_id
    venue_id = get_env("VENUE_ID", "stadium-001")
    pubsub = PubSubClient()
    firestore_client = FirestoreClient.get_instance()
    logger.info("incident_manager_started", venue_id=venue_id)


@app.post("/api/v1/incidents", response_model=IncidentResponse, status_code=201)
async def create_incident(request: CreateIncidentRequest):
    incident_id = f"inc-{uuid.uuid4().hex[:12]}"
    now = utc_now_iso()

    assigned = auto_assign_staff(request.category, request.severity)

    incident = {
        "incident_id": incident_id,
        "venue_id": venue_id,
        "category": request.category,
        "severity": request.severity,
        "status": IncidentStatus.OPEN,
        "zone_id": request.zone_id,
        "description": request.description,
        "reported_by": request.reported_by,
        "assigned_staff": assigned,
        "updates": [{
            "timestamp": now,
            "action": "created",
            "note": "Incident created",
            "by": request.reported_by,
        }],
        "created_at": now,
        "updated_at": now,
    }

    if assigned:
        incident["updates"].append({
            "timestamp": now,
            "action": "auto_assigned",
            "note": f"Auto-assigned to {assigned}",
            "by": "system",
        })

    INCIDENTS[incident_id] = incident

    pubsub.publish("incident.created", {
        "venue_id": venue_id,
        "incident_id": incident_id,
        "category": request.category,
        "severity": request.severity,
        "zone_id": request.zone_id,
        "description": request.description,
        "reported_by": request.reported_by,
        "event_time": now,
    })

    if assigned:
        pubsub.publish("notification.send", {
            "venue_id": venue_id,
            "notification_id": f"inc-notif-{incident_id}",
            "target_type": "staff",
            "target_id": assigned,
            "channel": "dashboard",
            "title": f"New {request.severity.value} Incident: {request.category.value}",
            "body": request.description,
            "data": {"incident_id": incident_id, "zone_id": request.zone_id},
            "event_time": now,
        })

    logger.info("incident_created", incident_id=incident_id, category=request.category, severity=request.severity)
    return IncidentResponse(**incident)


@app.get("/api/v1/incidents/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str):
    if incident_id not in INCIDENTS:
        raise HTTPException(status_code=404, detail="Incident not found")
    return IncidentResponse(**INCIDENTS[incident_id])


@app.patch("/api/v1/incidents/{incident_id}", response_model=IncidentResponse)
async def update_incident(incident_id: str, request: UpdateIncidentRequest):
    if incident_id not in INCIDENTS:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = INCIDENTS[incident_id]
    now = utc_now_iso()

    old_status = incident["status"]
    incident["status"] = request.status
    incident["updated_at"] = now

    if request.assigned_staff:
        incident["assigned_staff"] = request.assigned_staff

    update_entry = {
        "timestamp": now,
        "action": f"status_changed_{old_status}_to_{request.status}",
        "note": request.update_note or f"Status updated to {request.status}",
        "by": request.assigned_staff or "system",
    }
    incident["updates"].append(update_entry)

    pubsub.publish("incident.updated", {
        "venue_id": venue_id,
        "incident_id": incident_id,
        "status": request.status,
        "assigned_staff": incident["assigned_staff"],
        "update_note": request.update_note,
        "event_time": now,
    })

    logger.info("incident_updated", incident_id=incident_id, status=request.status)
    return IncidentResponse(**incident)


@app.get("/api/v1/incidents")
async def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    zone_id: str | None = None,
):
    results = list(INCIDENTS.values())

    if status:
        results = [i for i in results if i["status"] == status]
    if severity:
        results = [i for i in results if i["severity"] == severity]
    if category:
        results = [i for i in results if i["category"] == category]
    if zone_id:
        results = [i for i in results if i["zone_id"] == zone_id]

    results.sort(key=lambda x: SEVERITY_PRIORITY.get(x["severity"], 99))

    return {"incidents": results, "count": len(results)}


@app.get("/api/v1/incidents/dashboard/summary")
async def dashboard_summary():
    open_incidents = [i for i in INCIDENTS.values() if i["status"] in [IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED, IncidentStatus.IN_PROGRESS]]
    by_severity = {}
    by_category = {}
    for inc in open_incidents:
        sev = inc["severity"]
        cat = inc["category"]
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "venue_id": venue_id,
        "open_incidents": len(open_incidents),
        "by_severity": by_severity,
        "by_category": by_category,
        "critical_unassigned": sum(
            1 for i in open_incidents
            if i["severity"] == IncidentSeverity.CRITICAL and not i.get("assigned_staff")
        ),
        "timestamp": utc_now_iso(),
    }


@app.get("/health")
async def health():
    open_count = sum(1 for i in INCIDENTS.values() if i["status"] != IncidentStatus.CLOSED)
    return {
        "status": "healthy",
        "service": "incident-manager",
        "open_incidents": open_count,
        "total_incidents": len(INCIDENTS),
    }
