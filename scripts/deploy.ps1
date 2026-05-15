$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $projectDir

$command = if ($args.Count -eq 0) { "help" } else { $args[0] }

$VENUE_ID = if ($env:VENUE_ID) { $env:VENUE_ID } else { "stadium-001" }
$REGION = if ($env:REGION) { $env:REGION } else { "us-central1" }
$ENVIRONMENT = if ($env:ENVIRONMENT) { $env:ENVIRONMENT } else { "dev" }

function Log-Info($msg)  { Write-Host "[INFO] $msg" -ForegroundColor Green }
function Log-Warn($msg)  { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Log-Error($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red }

switch ($command) {
    "local" {
        Log-Info "Starting SSEP locally with Docker Compose"
        Set-Location $projectDir
        docker compose up --build -d
        Log-Info "Services starting. Check health:"
        Log-Info "  Crowd Flow:      http://localhost:8080/health"
        Log-Info "  Queue Predictor: http://localhost:8081/health"
        Log-Info "  Navigation:      http://localhost:8082/health"
        Log-Info "  Order & Deliver: http://localhost:8083/health"
        Log-Info "  Notification:    http://localhost:8084/health"
        Log-Info "  Incident Mgr:    http://localhost:8085/health"
        Log-Info "  Gate Entry:      http://localhost:8086/health"
    }
    "stop" {
        Log-Info "Stopping SSEP services"
        Set-Location $projectDir
        docker compose down
        Log-Info "All services stopped"
    }
    "status" {
        $ports = @(8080, 8081, 8082, 8083, 8084, 8085, 8086)
        $names = @("crowd-flow", "queue-predictor", "navigation", "order-deliver", "notification", "incident-manager", "gate-entry")
        for ($i = 0; $i -lt $ports.Count; $i++) {
            try {
                $resp = Invoke-WebRequest -Uri "http://localhost:$($ports[$i])/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
                Log-Info "$($names[$i]) (:$($ports[$i])) - HEALTHY"
            } catch {
                Log-Warn "$($names[$i]) (:$($ports[$i])) - DOWN"
            }
        }
    }
    "test" {
        Log-Info "Running unit tests for Python services"
        $services = @("crowd-flow", "queue-predictor", "order-deliver", "notification", "incident-manager", "gate-entry")
        foreach ($svc in $services) {
            Log-Info "Testing $svc..."
            Push-Location "$projectDir\services\$svc"
            python -m pytest test_main.py -v --tb=short 2>$null
            Pop-Location
        }
    }
    default {
        Write-Host "SSEP Deployment Script (Windows)"
        Write-Host ""
        Write-Host "Usage: .\deploy.ps1 {local|stop|status|test}"
        Write-Host ""
        Write-Host "Commands:"
        Write-Host "  local  - Start all services locally with Docker Compose"
        Write-Host "  stop   - Stop local Docker Compose services"
        Write-Host "  status - Check health of local services"
        Write-Host "  test   - Run unit tests for all services"
    }
}
