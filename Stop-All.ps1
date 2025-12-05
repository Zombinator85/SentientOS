#requires -version 5.1
<#!
Stop-All.ps1 - Gracefully stop SentientOS services on Windows
- Stops llama-server, relay, and runtime shells
- Frees ports 5000/8080/3928
- Warns about locked CUDA DLLs
- Verifies shutdown
!>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootPath = "C:\SentientOS"
$LlamaPort = 8080
$RelayPort = 3928
$RuntimePort = 5000

function Write-Status {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Fail {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
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
            Write-Status "Stopping PID $pid on port $Port"
            Stop-Process -Id $pid -Force -ErrorAction Stop
        } catch {
            Write-Warn "Unable to stop process $pid on port $Port: $($_.Exception.Message)"
        }
    }
}

function Stop-ByProcessName {
    param([string]$Name)
    $procs = Get-Process -Name $Name -ErrorAction SilentlyContinue
    foreach ($proc in $procs) {
        try {
            Write-Status "Stopping $Name (PID $($proc.Id))"
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
        } catch {
            Write-Warn "Unable to stop $Name (PID $($proc.Id)): $($_.Exception.Message)"
        }
    }
}

function Stop-PythonCommandLike {
    param([string]$Pattern)
    $matches = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { ($_.Name -match "python") -and ($_.CommandLine -match $Pattern) }
    foreach ($proc in $matches) {
        try {
            Write-Status "Stopping python PID $($proc.ProcessId) running $Pattern"
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        } catch {
            Write-Warn "Unable to stop PID $($proc.ProcessId): $($_.Exception.Message)"
        }
    }
}

function Test-UrlHealthy {
    param([string]$Url)
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $resp.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Detect-LockedCudaModules {
    $cudaModules = @("cudart64", "cublas64", "cublasLt64", "cudnn64")
    $locking = @()
    foreach ($proc in Get-Process -ErrorAction SilentlyContinue) {
        foreach ($name in $cudaModules) {
            try {
                if ($proc.Modules.FileName -match $name) {
                    $locking += "$($proc.ProcessName) (PID $($proc.Id))"
                    break
                }
            } catch {
                continue
            }
        }
    }
    if ($locking.Count -gt 0) {
        Write-Warn "CUDA DLLs still loaded by: $($locking -join ', '). Close these if startup later fails."
    } else {
        Write-Ok "No CUDA DLL locks detected."
    }
}

Write-Status "Stopping SentientOS services..."
Stop-ByProcessName -Name "llama-server"
Stop-PythonCommandLike -Pattern "relay_server.py"
Stop-PythonCommandLike -Pattern "cathedral_launcher.py"

Write-Status "Freeing ports $LlamaPort, $RelayPort, $RuntimePort"
Kill-PortOccupants -Port $LlamaPort
Kill-PortOccupants -Port $RelayPort
Kill-PortOccupants -Port $RuntimePort

$llamaAlive = Test-UrlHealthy -Url "http://127.0.0.1:$LlamaPort/"
$relayAlive = Test-UrlHealthy -Url "http://127.0.0.1:$RelayPort/v1/health"
$runtimeAlive = Test-UrlHealthy -Url "http://127.0.0.1:$RuntimePort/"

if ($llamaAlive -or $relayAlive -or $runtimeAlive) {
    Write-Warn "Some endpoints still respond (llama: $llamaAlive, relay: $relayAlive, runtime: $runtimeAlive)."
} else {
    Write-Ok "All endpoints report stopped."
}

Detect-LockedCudaModules

Write-Host "Shutdown complete. You can now re-run Start-All.ps1." -ForegroundColor Green
