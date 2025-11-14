Param(
    [string]$VenvPath = "$PSScriptRoot\..\venv"
)

$ErrorActionPreference = "Stop"
$root = "C:/SentientOS"
$logs = Join-Path $root "logs"
$runtimeLog = Join-Path $logs "runtime.log"
$env:PYTHONPATH = "$PSScriptRoot/.."

if (Test-Path $VenvPath) {
    . "$VenvPath\Scripts\Activate.ps1"
}

Write-Host "[SentientOS] Launching llama.cpp server..."
Start-Process -FilePath (Join-Path $root "bin/llama-server.exe") -ArgumentList "--model", (Join-Path $root "sentientos_data/models/default.gguf") -WindowStyle Hidden

Write-Host "[SentientOS] Launching Relay API server..."
Start-Process -FilePath "python" -ArgumentList "-m", "sentientos.oracle_relay", "--host", "127.0.0.1", "--port", "65432" -WindowStyle Hidden

Write-Host "[SentientOS] Launching runtime shell..."
Start-Process -FilePath "python" -ArgumentList "-m", "sentientos.start" -WorkingDirectory "$PSScriptRoot/.." -WindowStyle Hidden

Write-Host "[SentientOS] Opening log console..."
if (-not (Test-Path $runtimeLog)) {
    New-Item -ItemType File -Path $runtimeLog -Force | Out-Null
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Get-Content -Path '$runtimeLog' -Wait"
