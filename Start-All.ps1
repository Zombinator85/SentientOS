#requires -version 5.1
<#
Start-All.ps1 - One-click launcher for SentientOS on Windows
- Kills stale llama-server and relay instances
- Ensures ports 8080 (llama-server) and 3928 (relay) are free
- Activates the local .venv and validates dependencies
- Starts llama.cpp server, relay_server.py, and SentientOS runtime shell in separate windows
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Paths
$RootPath = "C:\SentientOS"
$VenvActivate = Join-Path $RootPath ".venv\\Scripts\\Activate.ps1"
$PythonExe = Join-Path $RootPath ".venv\\Scripts\\python.exe"
$LlamaExe = Join-Path $RootPath "bin\\llama-server.exe"
$ModelPath = Join-Path $RootPath "sentientos_data\\models\\mistral-7b\\mistral-7b-instruct-v0.2.Q4_K_M.gguf"
$RelayScript = Join-Path $RootPath "relay_server.py"
$CathedralLauncher = Join-Path $RootPath "cathedral_launcher.py"

# Configuration
$LlamaPort = 8080
$RelayPort = 3928
$LlamaHealthUrl = "http://127.0.0.1:$LlamaPort/"
$RelayHealthUrl = "http://127.0.0.1:$RelayPort/v1/health"
$StartupTimeoutSec = 90

function Write-Status {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Fail {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

function Ensure-PathExists {
    param([string]$Path, [string]$FriendlyName)
    if (-not (Test-Path $Path)) {
        Fail "$FriendlyName is missing: $Path"
    }
}

function Get-PortProcessIds {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $connections) { return @() }
    return $connections | Select-Object -ExpandProperty OwningProcess -Unique
}

function Kill-PortOccupants {
    param([int]$Port)
    $pids = Get-PortProcessIds -Port $Port
    foreach ($pid in $pids) {
        try {
            Write-Status "Killing process $pid on port $Port"
            Stop-Process -Id $pid -Force -ErrorAction Stop
        } catch {
            Fail "Unable to free port $Port from process $pid. Please close it manually and re-run."
        }
    }
}

function Kill-StaleProcesses {
    Write-Status "Stopping any existing llama-server.exe processes"
    $llamaProcs = Get-Process -Name "llama-server" -ErrorAction SilentlyContinue
    foreach ($proc in $llamaProcs) {
        try { Stop-Process -Id $proc.Id -Force } catch {}
    }

    Write-Status "Stopping any relay_server.py python processes"
    $relayCandidates = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { ($_.Name -match "python") -and ($_.CommandLine -match "relay_server.py") }
    foreach ($proc in $relayCandidates) {
        try { Stop-Process -Id $proc.ProcessId -Force } catch {}
    }
}

function Test-UrlHealthy {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Wait-ForHealth {
    param(
        [string]$Url,
        [int]$TimeoutSec,
        [string]$Name
    )
    $stopWatch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($stopWatch.Elapsed.TotalSeconds -lt $TimeoutSec) {
        if (Test-UrlHealthy -Url $Url) { return $true }
        Start-Sleep -Seconds 2
    }
    Fail "$Name did not become ready within $TimeoutSec seconds."
}

function Activate-Venv {
    Ensure-PathExists -Path $VenvActivate -FriendlyName ".venv activation script"
    Ensure-PathExists -Path $PythonExe -FriendlyName "Python interpreter in .venv"
    Write-Status "Activating virtual environment"
    try {
        . $VenvActivate
    } catch {
        Fail "Unable to activate virtual environment. Ensure ExecutionPolicy allows scripts."
    }
}

function Validate-PythonDependencies {
    Write-Status "Validating Python dependencies with 'pip check'"
    try {
        $pipCheck = & $PythonExe -m pip check 2>&1
        if ($LASTEXITCODE -ne 0) {
            Fail "Python dependencies are missing or broken. Output:`n$($pipCheck | Out-String)"
        }
    } catch {
        Fail "Unable to run pip check. Ensure Python and dependencies are installed in .venv."
    }
}

function Ensure-RelayScriptExists {
    Ensure-PathExists -Path $RelayScript -FriendlyName "relay_server.py"
}

function Ensure-LlamaAssets {
    Ensure-PathExists -Path $LlamaExe -FriendlyName "llama-server.exe"
    Ensure-PathExists -Path $ModelPath -FriendlyName "model file"
}

function Ensure-CathedralLauncher {
    Ensure-PathExists -Path $CathedralLauncher -FriendlyName "cathedral_launcher.py"
}

function Start-LlamaServer {
    Ensure-LlamaAssets

    if (Test-UrlHealthy -Url $LlamaHealthUrl) {
        Write-Ok "Model server already running on port $LlamaPort. Reusing existing instance."
        return
    }

    Kill-PortOccupants -Port $LlamaPort
    Write-Status "Launching llama.cpp server..."
    $command = "cd `"$RootPath`"; & `"$LlamaExe`" --host 127.0.0.1 --port $LlamaPort --model `"$ModelPath`""
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal | Out-Null

    Write-Status "Waiting for llama.cpp server to become ready on port $LlamaPort"
    Wait-ForHealth -Url $LlamaHealthUrl -TimeoutSec $StartupTimeoutSec -Name "llama-server"
    Write-Ok "Model server started"
}

function Start-RelayServer {
    Ensure-RelayScriptExists

    if (Test-UrlHealthy -Url $RelayHealthUrl) {
        Write-Ok "Relay server already running on port $RelayPort. Reusing existing instance."
        return
    }

    Kill-PortOccupants -Port $RelayPort
    Write-Status "Launching relay_server.py..."
    $command = "cd `"$RootPath`"; & `"$PythonExe`" `"$RelayScript`" --port $RelayPort"
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal | Out-Null

    Write-Status "Waiting for relay server to become ready on port $RelayPort"
    Wait-ForHealth -Url $RelayHealthUrl -TimeoutSec $StartupTimeoutSec -Name "relay_server"
    Write-Ok "Relay server online"
}

function Start-CathedralShell {
    Ensure-CathedralLauncher
    Write-Status "Launching SentientOS runtime shell (cathedral_launcher.py)"
    $command = "cd `"$RootPath`"; & `"$PythonExe`" `"$CathedralLauncher`""
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal | Out-Null
    Write-Ok "SentientOS runtime active"
}

Write-Status "Starting SentientOS stack..."
Ensure-PathExists -Path $RootPath -FriendlyName "SentientOS root directory"
Activate-Venv
Validate-PythonDependencies
Kill-StaleProcesses
Start-LlamaServer
Start-RelayServer
Start-CathedralShell

Write-Host "All services are running. This window will remain open for logs. Press Ctrl+C to close this launcher; the other windows will stay active." -ForegroundColor Yellow
