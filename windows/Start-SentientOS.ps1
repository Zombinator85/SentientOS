Param(
    [string]$VenvPath = "$PSScriptRoot\..\.venv"
)

$ErrorActionPreference = "Stop"
$launcher = Join-Path $PSScriptRoot "..\Start-All.ps1"
$logDir = Join-Path $PSScriptRoot "..\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$runtimeLog = Join-Path $logDir "runtime.log"

if (Test-Path $launcher) {
    Write-Host "[SentientOS] Delegating to Start-All.ps1 for full diagnostics..."
    & $launcher
    exit $LASTEXITCODE
}

Write-Warning "Start-All.ps1 not found; falling back to minimal startup."
$root = "C:/SentientOS"
$env:PYTHONPATH = "$PSScriptRoot/.."

if (Test-Path $VenvPath) {
    . "$VenvPath\Scripts\Activate.ps1"
} else {
    Write-Warning "Virtual environment not found at $VenvPath."
}

Write-Host "[SentientOS] Freeing ports 8080/3928/5000"
foreach ($port in 8080,3928,5000) {
    $pids = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid in $pids) { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue }
}

Write-Host "[SentientOS] Launching llama.cpp server..."
Start-Process -FilePath (Join-Path $root "bin/llama-server.exe") -ArgumentList "--model", "C:\SentientOS\sentientos_data\models\mistral-7b\mistral-7b-instruct-v0.2.Q4_K_M.gguf" -WindowStyle Hidden

Write-Host "[SentientOS] Launching Relay API server..."
Start-Process -FilePath "python" -ArgumentList "-m", "sentientos.oracle_relay", "--host", "127.0.0.1", "--port", "3928" -WindowStyle Hidden

Write-Host "[SentientOS] Waiting for Relay API to become available..."
$relayReady = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $check = Invoke-WebRequest -Uri "http://127.0.0.1:3928/ping" -UseBasicParsing -TimeoutSec 2 -Method GET
        if ($check.StatusCode -eq 200) { $relayReady = $true; break }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $relayReady) {
    Write-Warning "Relay API not reachable on port 3928; runtime may start without it."
}

Write-Host "[SentientOS] Launching runtime shell..."
Start-Process -FilePath "python" -ArgumentList "-m", "sentientos.start" -WorkingDirectory "$PSScriptRoot/.." -WindowStyle Hidden

Write-Host "[SentientOS] Opening log console..."
if (-not (Test-Path $runtimeLog)) { New-Item -ItemType File -Path $runtimeLog -Force | Out-Null }
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Get-Content -Path '$runtimeLog' -Wait"
