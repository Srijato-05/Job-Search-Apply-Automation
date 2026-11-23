# JobAutomation 1-Click Local Startup Script (Windows PowerShell)
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$UvicornExe = Join-Path $RepoRoot ".venv\Scripts\uvicorn.exe"
$DistIndex  = Join-Path $RepoRoot "frontend\dist\index.html"

if (-not (Test-Path $UvicornExe)) {
    Write-Host "ERROR: Virtual environment not found at .venv\Scripts\uvicorn.exe" -ForegroundColor Red
    Write-Host "Run: python -m venv .venv; .\.venv\Scripts\pip.exe install -r backend\requirements.txt" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $DistIndex)) {
    Write-Host "NOTE: frontend\dist not built yet. Building React dashboard or serving fallback..." -ForegroundColor Yellow
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Push-Location (Join-Path $RepoRoot "frontend")
        if (-not (Test-Path "node_modules")) { npm install }
        npm run build
        Pop-Location
    }
}

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  JobAutomation Local Copilot ($0, Local-First)" -ForegroundColor Cyan
Write-Host "  Dashboard : http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "  API Docs  : http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "  Extension : Load unpacked -> extension\dist" -ForegroundColor Gray
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

# Open default browser cleanly once Uvicorn responds on 127.0.0.1:8000
Start-Job -ScriptBlock {
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 1
            if ($resp.StatusCode -eq 200) {
                Start-Process "http://127.0.0.1:8000"
                break
            }
        } catch {}
    }
} | Out-Null

& $UvicornExe app.main:app --app-dir backend --host 127.0.0.1 --port 8000

