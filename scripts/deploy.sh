#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

VENUE_ID="${VENUE_ID:-stadium-001}"
REGION="${REGION:-us-central1}"
ENVIRONMENT="${ENVIRONMENT:-dev}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

deploy_infrastructure() {
  log_info "Deploying Terraform infrastructure for venue: $VENUE_ID"
  cd "$PROJECT_DIR/terraform/environments/$ENVIRONMENT"
  terraform init -backend-config="bucket=ssep-terraform-state-$ENVIRONMENT"
  terraform plan -var="project_id=$GOOGLE_CLOUD_PROJECT" -var="venue_id=$VENUE_ID" -var="region=$REGION" -out=tfplan
  terraform apply tfplan
  log_info "Infrastructure deployed successfully"
}

build_and_push_images() {
  log_info "Building and pushing container images"
  gcloud builds submit \
    --config="$PROJECT_DIR/cloudbuild/deploy-all.yaml" \
    --substitutions=_VENUE_ID="$VENUE_ID",_REGION="$REGION",_ENVIRONMENT="$ENVIRONMENT" \
    --project="$GOOGLE_CLOUD_PROJECT" \
    "$PROJECT_DIR"
  log_info "Images built and pushed to Artifact Registry"
}

run_unit_tests() {
  log_info "Running unit tests for Python services"
  for service in crowd-flow queue-predictor order-deliver notification incident-manager gate-entry; do
    log_info "Testing $service..."
    cd "$PROJECT_DIR/services/$service"
    pip install -q pytest httpx 2>/dev/null
    python -m pytest test_main.py -v --tb=short || log_warn "Tests for $service had issues"
  done
}

run_local() {
  log_info "Starting SSEP locally with Docker Compose"
  cd "$PROJECT_DIR"
  docker compose up --build -d
  log_info "Services starting. Wait ~30s then check http://localhost:8080/health"
  log_info "Crowd Flow:    http://localhost:8080"
  log_info "Queue Predictor: http://localhost:8081"
  log_info "Navigation:    http://localhost:8082"
  log_info "Order & Deliver: http://localhost:8083"
  log_info "Notification:  http://localhost:8084"
  log_info "Incident Mgr:  http://localhost:8085"
  log_info "Gate Entry:    http://localhost:8086"
}

stop_local() {
  log_info "Stopping local SSEP services"
  cd "$PROJECT_DIR"
  docker compose down
  log_info "All services stopped"
}

show_status() {
  log_info "SSEP Service Status"
  for port in 8080 8081 8082 8083 8084 8085 8086; do
    service_name=$(case $port in
      8080) echo "crowd-flow";;
      8081) echo "queue-predictor";;
      8082) echo "navigation";;
      8083) echo "order-deliver";;
      8084) echo "notification";;
      8085) echo "incident-manager";;
      8086) echo "gate-entry";;
    esac)
    status=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/health" 2>/dev/null || echo "000")
    if [ "$status" = "200" ]; then
      log_info "$service_name (:$port) - ${GREEN}HEALTHY${NC}"
    else
      log_warn "$service_name (:$port) - ${RED}DOWN ($status)${NC}"
    fi
  done
}

case "${1:-help}" in
  deploy)
    deploy_infrastructure
    build_and_push_images
    ;;
  infra)
    deploy_infrastructure
    ;;
  build)
    build_and_push_images
    ;;
  test)
    run_unit_tests
    ;;
  local)
    run_local
    ;;
  stop)
    stop_local
    ;;
  status)
    show_status
    ;;
  help|*)
    echo "SSEP Deployment Script"
    echo ""
    echo "Usage: $0 {deploy|infra|build|test|local|stop|status}"
    echo ""
    echo "Commands:"
    echo "  deploy   - Full deployment: infra + build + push"
    echo "  infra    - Deploy Terraform infrastructure only"
    echo "  build    - Build and push container images only"
    echo "  test     - Run unit tests for all services"
    echo "  local    - Start all services locally with Docker Compose"
    echo "  stop     - Stop local Docker Compose services"
    echo "  status   - Check health of local services"
    echo ""
    echo "Environment variables:"
    echo "  VENUE_ID       - Venue identifier (default: stadium-001)"
    echo "  REGION         - GCP region (default: us-central1)"
    echo "  ENVIRONMENT    - dev|staging|prod (default: dev)"
    ;;
esac
