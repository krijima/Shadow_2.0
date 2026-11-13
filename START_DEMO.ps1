# ==============================================================================
# SHADOW — Automated Hackathon Demo Launcher (PowerShell)
# DevHack 2026: "The Agent That Fights Dark Patterns"
# ==============================================================================

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "   SHADOW — The Dark Pattern Detection Agent (DevHack 2026)" -ForegroundColor Cyan
Write-Host "   Tagline: Detect. Defend. Act." -ForegroundColor DarkCyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# 1. Check Python
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonExe) {
    Write-Host "[ERROR] Python was not found in PATH." -ForegroundColor Red
    exit 1
}
Write-Host "[1/5] Python detected: $PythonExe" -ForegroundColor Green

# 2. Check Backend (:8001) — Safe reuse & non-destructive conflict reporting
$BackendListening = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
$BackendHealthy = $false

if ($BackendListening) {
    try {
        $HealthTest = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/health" -Method Get -TimeoutSec 2 -ErrorAction Stop
        if ($HealthTest.status -eq 'ok') {
            $BackendHealthy = $true
            Write-Host "[2/5] Backend is already running and healthy on http://127.0.0.1:8001 (Reused)." -ForegroundColor Green
        }
    } catch {
        $BackendHealthy = $false
    }

    if (-not $BackendHealthy) {
        $PidList = ($BackendListening | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
        Write-Host "[2/5] Warning: Port 8001 is listening (PID $PidList) but not responding to SHADOW health check." -ForegroundColor Yellow
        Write-Host "      Will attempt to verify connection during health check without terminating listener." -ForegroundColor DarkYellow
    }
} else {
    Write-Host "[2/5] Starting FastAPI backend on http://127.0.0.1:8001 ..." -ForegroundColor Yellow
    Start-Process -FilePath "python" -ArgumentList "-m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8001 --reload" -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

# 3. Check StreamCove (:8080) — Safe reuse & non-destructive conflict reporting
$StreamCoveListening = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
$StreamCoveHealthy = $false

if ($StreamCoveListening) {
    try {
        $SubTest = Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/subscription?user_id=demo" -Method Get -TimeoutSec 2 -ErrorAction Stop
        if ($SubTest.status) {
            $StreamCoveHealthy = $true
            Write-Host "[3/5] StreamCove is already running and healthy on http://127.0.0.1:8080 (Reused)." -ForegroundColor Green
        }
    } catch {
        $StreamCoveHealthy = $false
    }

    if (-not $StreamCoveHealthy) {
        $PidListSC = ($StreamCoveListening | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
        Write-Host "[3/5] Warning: Port 8080 is listening (PID $PidListSC) but not responding to StreamCove subscription API." -ForegroundColor Yellow
    }
} else {
    Write-Host "[3/5] Starting StreamCove service on http://127.0.0.1:8080 ..." -ForegroundColor Yellow
    Start-Process -FilePath "python" -ArgumentList "-m uvicorn server:app --app-dir streamcove --host 127.0.0.1 --port 8080 --reload" -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

# 4. Health Check Verification
Write-Host "[4/5] Verifying API health..." -ForegroundColor Yellow
$MaxRetries = 10
$Ready = $false

for ($i = 1; $i -le $MaxRetries; $i++) {
    try {
        $BackendRes = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/health" -Method Get -TimeoutSec 2
        $StreamRes = Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/subscription?user_id=demo" -Method Get -TimeoutSec 2
        if ($BackendRes.status -eq 'ok' -and $StreamRes.status) {
            $Ready = $true
            $GeminiState = if ($BackendRes.gemini_configured) { "Configured (Ready)" } else { "Unconfigured (Local fallback)" }
            Write-Host "      Backend (:8001):    OK" -ForegroundColor Green
            Write-Host "      StreamCove (:8080): OK (Subscription: $($StreamRes.status.ToUpper()))" -ForegroundColor Green
            Write-Host "      Gemini Engine:      $GeminiState" -ForegroundColor Cyan
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $Ready) {
    Write-Host "[WARNING] One or more services did not respond within 10 seconds. Check console logs." -ForegroundColor Red
}

# 5. Launch Demo Control Center
Write-Host "[5/5] Launching Demo Control Center in browser..." -ForegroundColor Green
Start-Process "http://127.0.0.1:8080/static/demo_control.html"

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "   SHADOW DEMO ENVIRONMENT READY!" -ForegroundColor Green
Write-Host "   - Demo Control Center: http://127.0.0.1:8080/static/demo_control.html" -ForegroundColor White
Write-Host "   - StreamCove Demo:     http://127.0.0.1:8080/static/index.html" -ForegroundColor White
Write-Host "   - Backend Swagger API: http://127.0.0.1:8001/docs" -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""
