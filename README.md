# Smart Stadium Experience Platform (SSEP)

Real-time, event-driven microservices system for large-scale sporting venues on Google Cloud Run.

## Architecture

```
IoT Sensors (BLE/WiFi) ──► Pub/Sub ──► Crowd Flow Service ──► Firestore
                                      │                        │
                                      ▼                        ▼
                              Queue Predictor (ML)     Navigation Service (Go)
                                      │                        │
                                      ▼                        ▼
                                 Redis Cache ──────► Attendee Mobile App
                                                               │
Gate Scans ──► Pub/Sub ──► Gate Entry Service                │
                                                               │
Staff Dashboard ◄── Notification Service ◄── Pub/Sub ────────┘
                                                               │
                    Incident Manager ◄── Pub/Sub ─────────────┘
                                                               │
              Order & Deliver Service ◄── Mobile App ──────────┘
```

## Services

| Service | Language | Port | Description |
|---------|----------|------|-------------|
| crowd-flow | Python | 8080 | BLE/WiFi sensor ingestion, heat-map engine |
| queue-predictor | Python | 8081 | ML wait-time predictions (XGBoost) |
| navigation | Go | 8082 | Dijkstra-based routing with congestion weights |
| order-deliver | Python | 8083 | Seat-side food/drink ordering |
| notification | Python | 8084 | Real-time staff task assignments, push alerts |
| incident-manager | Python | 8085 | Staff operations dashboard, incident tracking |
| gate-entry | Python | 8086 | Gate scan events, entry velocity tracking |

## Quick Start

```bash
# Deploy infrastructure
cd terraform/environments/dev
terraform init && terraform apply -var="venue_id=stadium-001"

# Deploy all services
gcloud builds submit --config=cloudbuild/deploy-all.yaml

# Run locally with Docker Compose
docker compose up
```

## Event Topics (Pub/Sub)

- `crowd.density.updated` — zone density changes
- `queue.wait.changed` — wait-time estimates updated
- `gate.scan.event` — ticket scan at entry gates
- `order.created` / `order.status.changed` — food orders
- `incident.created` / `incident.updated` — staff incidents
- `notification.send` — push notification requests
