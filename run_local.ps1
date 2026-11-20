# StudioTrack AI - Local Development Runner
# Starts both the FastAPI backend and Vite frontend with SQLite and mock email outbox.

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "      Starting StudioTrack AI Locally     " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

$RootDir = $PSScriptRoot
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"

# 1. Verify virtual environment
if (-not (Test-Path $PythonExe)) {
    Write-Host "[1/4] Creating backend virtual environment..." -ForegroundColor Yellow
    python -m venv (Join-Path $BackendDir ".venv")
    & $PythonExe -m pip install -r (Join-Path $BackendDir "requirements.txt")
} else {
    Write-Host "[1/4] Backend environment verified." -ForegroundColor Green
}

# 2. Check and initialize SQLite database
Push-Location $BackendDir
try {
    Write-Host "[2/4] Applying database migrations..." -ForegroundColor Yellow
    & $PythonExe -m alembic upgrade head

    Write-Host "[2/4] Seeding demo studio data..." -ForegroundColor Yellow
    & $PythonExe -m scripts.seed_demo
} finally {
    Pop-Location
}

# 3. Check frontend dependencies
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "[3/4] Installing frontend npm dependencies..." -ForegroundColor Yellow
    npm --prefix $FrontendDir install
} else {
    Write-Host "[3/4] Frontend dependencies verified." -ForegroundColor Green
}

Write-Host "[4/4] Starting backend (port 8000) and frontend (port 5173)..." -ForegroundColor Cyan
Write-Host "Demo Accounts available at http://localhost:5173:" -ForegroundColor Green
Write-Host "  - Admin:  admin@studiotrack.demo        (Admin@12345)" -ForegroundColor Gray
Write-Host "  - Lead:   lead.anim@studiotrack.demo    (Lead@12345)" -ForegroundColor Gray
Write-Host "  - Artist: artist.arjun@studiotrack.demo (Artist@12345)" -ForegroundColor Gray
Write-Host "`nPress Ctrl+C to terminate both servers.`n" -ForegroundColor Yellow

# Start backend process
$BackendProcess = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m uvicorn app.main:app --reload --port 8000" `
    -WorkingDirectory $BackendDir `
    -PassThru

# Start frontend in current window or process
try {
    Push-Location $FrontendDir
    npm run dev
} finally {
    Pop-Location
    if ($BackendProcess -and -not $BackendProcess.HasExited) {
        Write-Host "`nStopping backend server..." -ForegroundColor Yellow
        Stop-Process -Id $BackendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "StudioTrack AI stopped." -ForegroundColor Green
}

