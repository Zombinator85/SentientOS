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
$ConfigDir = Join-Path $RootPath "config"
$ModelPreferencePath = Join-Path $ConfigDir "model_preference.txt"
$VenvPath = Join-Path $RootPath ".venv"
$VenvActivate = Join-Path $VenvPath "Scripts\\Activate.ps1"
$PythonExe = Join-Path $VenvPath "Scripts\\python.exe"
$LlamaExe = Join-Path $RootPath "bin\\llama-server.exe"
$RelayScript = Join-Path $RootPath "relay_server.py"
$CathedralLauncher = Join-Path $RootPath "cathedral_launcher.py"
$ModelsDir = Join-Path $RootPath "sentientos_data\\models"
$DefaultModel = Join-Path $ModelsDir "mistral-7b\\mistral-7b-instruct-v0.2.Q4_K_M.gguf"

# Configuration
$LlamaPort = 8080
$RelayPort = 3928
$RuntimePort = 5000
$LlamaHealthUrl = "http://127.0.0.1:$LlamaPort/"
$RelayHealthUrl = "http://127.0.0.1:$RelayPort/v1/health"
$StartupTimeoutSec = 90
$HealthRetrySeconds = 10
$MaxComponentRetries = 3
$RequiredPythonVersion = "3.11"
$RequiredLlamaCppVersion = "0.2.90"
$DefaultModelUrl = "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf?download=1"

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

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
        Write-Warn "CUDA DLLs remain loaded by: $($locking -join ', '). Close these to avoid startup conflicts."
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
    return $false
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

function Ensure-PythonVersion {
    Write-Status "Checking for Python $RequiredPythonVersion"
    $pythonVersionOutput = & py -$RequiredPythonVersion --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Fail "Python $RequiredPythonVersion is required. Install it from https://www.python.org/downloads/release/python-311/"
    }
    $version = ($pythonVersionOutput -replace "Python", "").Trim()
    if (-not $version.StartsWith($RequiredPythonVersion)) {
        Fail "Python $RequiredPythonVersion is required but found $version"
    }
    Write-Ok "Python $version detected"
}

function Ensure-Venv {
    if (-not (Test-Path $VenvActivate)) {
        Write-Status "First run detected: creating virtual environment (.venv)"
        try {
            & py -$RequiredPythonVersion -m venv $VenvPath
        } catch {
            Fail "Failed to create virtual environment. $_"
        }
    }
}

function Ensure-Dependencies {
    Write-Status "Installing/validating Python dependencies"
    try {
        & $PythonExe -m pip install --upgrade pip | Out-Null
        & $PythonExe -m pip install -r (Join-Path $RootPath "requirements.txt")
        & $PythonExe -m pip install "llama-cpp-python==$RequiredLlamaCppVersion"
    } catch {
        Fail "Dependency installation failed. $_"
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
}

function Ensure-CathedralLauncher {
    Ensure-PathExists -Path $CathedralLauncher -FriendlyName "cathedral_launcher.py"
}

function Get-ModelQuantizationScore {
    param([string]$Path)
    $file = Split-Path $Path -Leaf
    if ($file -match "Q(?<level>\d+)") {
        return [int]$Matches['level']
    }
    return 0
}

function Select-ModelPath {
    Ensure-Directory -Path $ModelsDir
    $models = Get-ChildItem -Path $ModelsDir -Filter "*.gguf" -Recurse -ErrorAction SilentlyContinue
    if (-not $models) {
        Write-Warn "No GGUF models found. Downloading default model..."
        Ensure-Directory -Path (Split-Path $DefaultModel -Parent)
        try {
            Invoke-WebRequest -Uri $DefaultModelUrl -OutFile $DefaultModel
        } catch {
            Fail "Unable to download default model from $DefaultModelUrl. $_"
        }
        $models = @(Get-Item $DefaultModel)
    }

    if (Test-Path $ModelPreferencePath) {
        $preferred = Get-Content $ModelPreferencePath -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($preferred -and (Test-Path $preferred)) {
            Write-Status "Using stored model preference: $preferred"
            return $preferred
        }
    }

    if ($models.Count -eq 1) { return $models[0].FullName }

    $sorted = $models | Sort-Object @{ Expression = { Get-ModelQuantizationScore $_.FullName }; Descending = $true }, @{ Expression = { $_.LastWriteTimeUtc }; Descending = $true }
    $best = $sorted | Select-Object -First 1
    Write-Warn "Multiple models found. Selected highest quantization + newest: $($best.FullName)"

    $answer = Read-Host "Use this model? (Y to accept, or enter path to choose another)"
    if ($answer -and $answer -ne "" -and $answer -notmatch "^[Yy]$") {
        if (-not (Test-Path $answer)) {
            Write-Warn "Provided path not found; defaulting to $($best.FullName)"
        } else {
            $best = Get-Item $answer
        }
    }

    Ensure-Directory -Path $ConfigDir
    $best.FullName | Out-File -FilePath $ModelPreferencePath -Force -Encoding utf8
    return $best.FullName
}

function Test-PlaceholderModel {
    param([string]$Path)
    $fileInfo = Get-Item $Path
    if ($fileInfo.Length -lt 100MB) {
        Write-Warn "Model file appears small ($([math]::Round($fileInfo.Length/1MB,2)) MB). Placeholder model suspected."
    }
}

function Start-LlamaServer {
    Ensure-LlamaAssets

    if (Test-UrlHealthy -Url $LlamaHealthUrl) {
        Write-Ok "Model server already running on port $LlamaPort. Reusing existing instance."
        return
    }

    Kill-PortOccupants -Port $LlamaPort
    Write-Status "Launching llama.cpp server (logging window will stay open)"
    $command = "cd `"$RootPath`"; Write-Host 'Launching llama-server on port $LlamaPort using model $ModelPath' -ForegroundColor Yellow; & `"$LlamaExe`" --host 127.0.0.1 --port $LlamaPort --model `"$ModelPath`""
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal -WorkingDirectory $RootPath | Out-Null

    Write-Status "Waiting up to $HealthRetrySeconds seconds for llama.cpp server health..."
    if (-not (Wait-ForHealth -Url $LlamaHealthUrl -TimeoutSec $HealthRetrySeconds -Name "llama-server")) {
        throw "llama-server did not become healthy in time"
    }
    Write-Ok "Model server started"
}

function Start-RelayServer {
    Ensure-RelayScriptExists

    if (Test-UrlHealthy -Url $RelayHealthUrl) {
        Write-Ok "Relay server already running on port $RelayPort. Reusing existing instance."
        return
    }

    Kill-PortOccupants -Port $RelayPort
    Write-Status "Launching relay_server.py (logging window will stay open)"
    $command = "cd `"$RootPath`"; Write-Host 'Launching relay on port $RelayPort' -ForegroundColor Yellow; & `"$PythonExe`" `"$RelayScript`" --port $RelayPort"
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal -WorkingDirectory $RootPath | Out-Null

    Write-Status "Waiting up to $HealthRetrySeconds seconds for relay health..."
    if (-not (Wait-ForHealth -Url $RelayHealthUrl -TimeoutSec $HealthRetrySeconds -Name "relay_server")) {
        throw "relay_server did not become healthy in time"
    }
    Write-Ok "Relay server online"
}

function Start-CathedralShell {
    Ensure-CathedralLauncher
    Write-Status "Launching SentientOS runtime shell (cathedral_launcher.py)"
    $command = "cd `"$RootPath`"; Write-Host 'Starting runtime shell on port $RuntimePort (if applicable)' -ForegroundColor Yellow; & `"$PythonExe`" `"$CathedralLauncher`""
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal -WorkingDirectory $RootPath | Out-Null
    Write-Ok "SentientOS runtime active"
}

function Retry-Component {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    for ($i = 1; $i -le $MaxComponentRetries; $i++) {
        try {
            & $Action
            return
        } catch {
            Write-Warn "$Name attempt $i failed: $($_.Exception.Message)"
            if ($i -lt $MaxComponentRetries) {
                Write-Status "Retrying $Name..."
                Start-Sleep -Seconds 2
            } else {
                Fail "$Name failed after $MaxComponentRetries attempts. Check the log windows for details."
            }
        }
    }
}

function Ensure-HardwareSupport {
    Write-Status "Checking hardware capabilities (CUDA/AVX)"
    $gpuInfo = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue
    if (-not $gpuInfo) { Write-Warn "No GPU detected. Running in CPU/AVX mode." }

    $cudaDlls = @(Get-ChildItem -Path (Split-Path $LlamaExe -Parent) -Filter "cudart64*.dll" -ErrorAction SilentlyContinue)
    if ($gpuInfo -and -not $cudaDlls) {
        Write-Warn "GPU detected but CUDA runtime DLLs were not found near llama-server.exe."
    }

    $avxSupported = $false
    try {
        $avxSupported = [System.Runtime.Intrinsics.X86.Avx]::IsSupported
    } catch {}
    if (-not $avxSupported) {
        Write-Warn "AVX is not reported as supported. Use CPU-friendly quantization (Q4_K)."
    }
}

function Ensure-DesktopShortcut {
    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop "SentientOS.lnk"
    $targetPath = Join-Path $RootPath "Start-All.ps1"
    if (-not (Test-Path $shortcutPath)) {
        Write-Status "Creating desktop shortcut: $shortcutPath"
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = "powershell.exe"
        $shortcut.Arguments = "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$targetPath`""
        $shortcut.WorkingDirectory = $RootPath
        $shortcut.Description = "Launch SentientOS"
        $shortcut.Save()
    }
}

Write-Status "Starting SentientOS stack..."
Ensure-PathExists -Path $RootPath -FriendlyName "SentientOS root directory"
Ensure-Directory -Path $ConfigDir
Ensure-PythonVersion
Ensure-Venv
Activate-Venv
Ensure-Dependencies
Validate-PythonDependencies
Ensure-HardwareSupport
$ModelPath = Select-ModelPath
Test-PlaceholderModel -Path $ModelPath
Kill-StaleProcesses
Retry-Component -Name "llama-server" -Action { Start-LlamaServer }
Retry-Component -Name "relay_server" -Action { Start-RelayServer }
Retry-Component -Name "runtime" -Action { Start-CathedralShell }
Detect-LockedCudaModules
Ensure-DesktopShortcut

Write-Host "All services are running. This window will remain open for logs. Press Ctrl+C to close this launcher; the other windows will stay active." -ForegroundColor Yellow
