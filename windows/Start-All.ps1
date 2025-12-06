#requires -version 5.1
<#
Start-All.ps1 - Stable launcher for SentientOS on Windows
- Hard-binds to the shipped mistral GGUF model (no auto-downloads)
- Validates virtualenv, required Python modules, and hardware support
- Starts llama.cpp -> relay -> runtime in order with retries and logging
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Join-Path $PSScriptRoot ".."
Set-Location $Root

$LogPath = Join-Path $Root "logs\startup.log"
$ModelPath = "C:\SentientOS\sentientos_data\models\mistral-7b\mistral-7b-instruct-v0.2.Q4_K_M.gguf"
$MinimumModelBytes = 3GB
$VenvPython = ".\.venv\Scripts\python.exe"
$RelayPort = 3928
$LlamaPort = 8080
$RuntimeScript = "sentient_shell.py"
$RelayScript = "relay_server.py"
$CudaSearchPaths = @(
    "C:\\Windows\\System32",
    "C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin"
)

function Write-Log {
    param(
        [string]$Level,
        [string]$Message
    )
    $timestamp = (Get-Date).ToString("s")
    $line = "[$timestamp][$Level] $Message"
    if (-not (Test-Path $LogPath)) {
        $dir = Split-Path $LogPath -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        New-Item -ItemType File -Path $LogPath -Force | Out-Null
    }
    Add-Content -Path $LogPath -Value $line
    $color = switch ($Level) {
        "INFO" { "Cyan" }
        "WARN" { "Yellow" }
        "ERROR" { "Red" }
        default { "Gray" }
    }
    Write-Host $line -ForegroundColor $color
}

function Assert-File {
    param([string]$Path, [string]$Description)
    if (-not (Test-Path $Path)) {
        Write-Log -Level "ERROR" -Message "Missing $Description at $Path"
        exit 1
    }
}

function Assert-Model {
    Assert-File -Path $ModelPath -Description "GGUF model"
    $info = Get-Item $ModelPath
    if ($info.Length -lt $MinimumModelBytes) {
        Write-Log -Level "ERROR" -Message "Model file too small ($($info.Length) bytes). Expected >= $MinimumModelBytes."
        exit 1
    }
}

function Assert-Venv {
    Assert-File -Path $VenvPython -Description ".venv Python interpreter"
}

function Assert-Modules {
    $mods = @("llama_cpp", "fastapi", "python_multipart", "pygments", "cpuinfo")
    foreach ($m in $mods) {
        & $VenvPython - <<PY
import importlib, sys
try:
    importlib.import_module("$m")
except Exception:
    sys.exit(1)
PY
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Level "ERROR" -Message "Missing Python module: $m"
            exit 1
        }
    }
}

function Enable-CudaPaths {
    foreach ($path in $CudaSearchPaths) {
        if (Test-Path $path) {
            $env:PATH = "$path;$($env:PATH)"
        }
    }
    $found = $false
    foreach ($path in $CudaSearchPaths) {
        if (Get-ChildItem -Path $path -Filter "cudart64*.dll" -ErrorAction SilentlyContinue) {
            $found = $true
            break
        }
    }
    if ($found) {
        Write-Log -Level "INFO" -Message "CUDA runtime detected in search paths."
    } else {
        Write-Log -Level "WARN" -Message "CUDA runtime DLLs not discovered; proceeding with CPU/offload fallback."
    }
}

function Kill-Port {
    param([int]$Port)
    $matches = netstat -ano | Select-String ":$Port"
    foreach ($line in $matches) {
        $pid = ($line -split "\s+")[-1]
        if ($pid -match "^\d+$") {
            Write-Log -Level "INFO" -Message "Killing stale PID $pid on port $Port"
            try { taskkill /PID $pid /F | Out-Null } catch {}
        }
    }
}

function Wait-Port {
    param([int]$Port, [int]$Attempts = 5)
    for ($i = 0; $i -lt $Attempts; $i++) {
        $hit = netstat -ano | Select-String ":$Port"
        if ($hit) { return $true }
        $sleep = [Math]::Pow(2, $i)
        Start-Sleep -Seconds $sleep
    }
    return $false
}

function Invoke-WithRetry {
    param(
        [string]$Name,
        [scriptblock]$Action,
        [int]$Attempts = 3
    )
    for ($i = 1; $i -le $Attempts; $i++) {
        try {
            & $Action
            return
        } catch {
            Write-Log -Level "WARN" -Message "$Name attempt $i failed: $($_.Exception.Message)"
            if ($i -eq $Attempts) { throw }
            Start-Sleep -Seconds ([Math]::Pow(2, $i))
        }
    }
}

function Start-Llama {
    Write-Log -Level "INFO" -Message "Starting llama.cpp server..."
    Kill-Port -Port $LlamaPort
    Start-Process "./bin/llama-server.exe" "--host 127.0.0.1 --port $LlamaPort --model `"$ModelPath`" --ctx-size 8192 --gpu-layers 999" -WindowStyle Minimized
    if (-not (Wait-Port -Port $LlamaPort -Attempts 5)) {
        throw "llama.cpp failed to bind port $LlamaPort"
    }
    Write-Log -Level "INFO" -Message "llama.cpp server listening on $LlamaPort"
}

function Start-Relay {
    Write-Log -Level "INFO" -Message "Starting relay server..."
    Kill-Port -Port $RelayPort
    Start-Process powershell "-NoExit -Command `"& $VenvPython $RelayScript`"" | Out-Null
    if (-not (Wait-Port -Port $RelayPort -Attempts 5)) {
        throw "Relay failed to bind port $RelayPort"
    }
    Write-Log -Level "INFO" -Message "Relay server listening on $RelayPort"
}

function Start-Runtime {
    Write-Log -Level "INFO" -Message "Starting SentientOS runtime shell..."
    Start-Process powershell "-NoExit -Command `"& $VenvPython $RuntimeScript`"" | Out-Null
}

Write-Log -Level "INFO" -Message "Launching SentientOS stack from $Root"
Assert-Model
Assert-Venv
Assert-Modules
Enable-CudaPaths

foreach ($p in @($RelayPort, $LlamaPort)) { Kill-Port -Port $p }

try {
    Invoke-WithRetry -Name "llama.cpp" -Action { Start-Llama }
    Invoke-WithRetry -Name "relay" -Action { Start-Relay }
} catch {
    Write-Log -Level "ERROR" -Message $_
    exit 1
}
Start-Runtime

Write-Log -Level "INFO" -Message "Startup complete."
