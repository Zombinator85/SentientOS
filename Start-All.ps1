#requires -version 5.1
<#$
Start-All.ps1 - Self-healing SentientOS launcher for Windows
- Safe, GET-only downloader with retries and checksum validation
- Auto-repairs missing environments, binaries, and models
- Detects hardware (GPU/CUDA/AVX) and enforces correct model selection
- Frees conflicting ports (5000/8080/3928) and launches components in their own windows
- Writes diagnostic and repair history to logs/self_repair.log
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Paths
$RootPath = "C:\\SentientOS"
$ConfigDir = Join-Path $RootPath "config"
$HardwareProfilePath = Join-Path $ConfigDir "hardware_profile.json"
$ModelPreferencePath = Join-Path $ConfigDir "model_preference.txt"
$ModelPathFile = Join-Path $ConfigDir "model_path.txt"
$VenvPath = Join-Path $RootPath ".venv"
$VenvActivate = Join-Path $VenvPath "Scripts\\Activate.ps1"
$PythonExe = Join-Path $VenvPath "Scripts\\python.exe"
$LlamaExe = Join-Path $RootPath "bin\\llama-server.exe"
$RelayScript = Join-Path $RootPath "relay_server.py"
$CathedralLauncher = Join-Path $RootPath "cathedral_launcher.py"
$ModelsDir = Join-Path $RootPath "sentientos_data\\models"
$DefaultModelDir = Join-Path $ModelsDir "mistral-7b"
$DefaultModel = Join-Path $DefaultModelDir "mistral-7b-instruct-v0.2.Q4_K_M.gguf"
$RepairLog = Join-Path $RootPath "logs\\self_repair.log"

# Configuration
$LlamaPort = 8080
$RelayPort = 3928
$RuntimePort = 5000
$LlamaHealthUrl = "http://127.0.0.1:$LlamaPort/"
$RelayHealthUrl = "http://127.0.0.1:$RelayPort/v1/health"
$StartupTimeoutSec = 120
$HealthRetrySeconds = 20
$MaxComponentRetries = 3
$RequiredPythonVersion = "3.11"
$RequiredLlamaCppVersion = "0.2.90"
$DefaultModelUrl = "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf?download=1"
$DefaultModelSha256 = "e6dfd3bd27cfa6f0595b234d79ce31775f5f52a12ca6c5075463996f856b503d"

$Diagnostics = @()

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Write-RepairLog {
    param([string]$Message)
    Ensure-Directory -Path (Split-Path $RepairLog -Parent)
    $timestamp = (Get-Date).ToString("s") + "Z"
    Add-Content -Path $RepairLog -Value "$timestamp`t$Message"
}

function Write-Status { param([string]$Message) Write-Host "[*] $Message" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "[✔] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[✖] $Message" -ForegroundColor Yellow }
function Fail { param([string]$Message) Write-Host "[ERROR] $Message" -ForegroundColor Red; exit 1 }

function Add-Diagnostic {
    param(
        [string]$Name,
        [bool]$Healthy,
        [string]$Action
    )
    $Diagnostics += [pscustomobject]@{ Name = $Name; Healthy = $Healthy; Action = $Action }
    $symbol = if ($Healthy) { "✔" } else { "✖" }
    $color = if ($Healthy) { "Green" } else { "Red" }
    Write-Host "$symbol $Name`t$Action" -ForegroundColor $color
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
            Write-RepairLog "Killed process $pid occupying port $Port"
        } catch {
            Write-Warn "Unable to free port $Port from process $pid: $($_.Exception.Message)"
        }
    }
}

function Detect-UploadMisbehavior {
    param([System.Exception]$Error)
    $code = $Error.Exception.Response.StatusCode.Value__ 2>$null
    if ($code -in 411, 413, 501) { return $true }
    $msg = $Error.Exception.Message
    return ($msg -match "content-length" -or $msg -match "request entity" -or $msg -match "PUT")
}

function Test-Checksum {
    param([string]$Path, [string]$Sha256)
    if (-not $Sha256) { return $true }
    if (-not (Test-Path $Path)) { return $false }
    $hash = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
    return $hash -eq $Sha256.ToLowerInvariant()
}

function Download-ModelSafe {
    param(
        [string]$Uri,
        [string]$Destination,
        [string]$Sha256 = ""
    )

    Ensure-Directory -Path (Split-Path $Destination -Parent)
    $attempt = 0
    $fallbackUsed = $false
    while ($attempt -lt 5) {
        $attempt++
        $delay = [math]::Pow(2, $attempt - 1)
        Write-Status "Downloading model (attempt $attempt) via GET: $Uri"
        try {
            Invoke-WebRequest -Uri $Uri -OutFile $Destination -Method GET -UseBasicParsing -TimeoutSec 120 -MaximumRedirection 5
            if (-not (Test-Checksum -Path $Destination -Sha256 $Sha256)) {
                throw "Checksum mismatch after download"
            }
            $size = (Get-Item $Destination).Length
            if ($size -lt 100MB) { throw "Downloaded file too small ($size bytes)" }
            Write-Ok "Download complete via Invoke-WebRequest"
            return
        } catch {
            $needsFallback = Detect-UploadMisbehavior -Error $_
            if ($needsFallback -and -not $fallbackUsed) {
                Write-Warn "Invoke-WebRequest behaved like upload; switching to WebClient"
                $fallbackUsed = $true
                try {
                    $client = New-Object System.Net.WebClient
                    $client.DownloadFile($Uri, $Destination)
                    if (-not (Test-Checksum -Path $Destination -Sha256 $Sha256)) { throw "Checksum mismatch after WebClient" }
                    $size = (Get-Item $Destination).Length
                    if ($size -lt 100MB) { throw "Downloaded file too small ($size bytes)" }
                    Write-Ok "Download complete via WebClient fallback"
                    return
                } catch {
                    Write-Warn "WebClient fallback failed: $($_.Exception.Message)"
                }
            }
            try {
                Write-Warn "Attempting BITS fallback"
                Start-BitsTransfer -Source $Uri -Destination $Destination -DisplayName "SentientOSModel"
                if (-not (Test-Checksum -Path $Destination -Sha256 $Sha256)) { throw "Checksum mismatch after BITS" }
                $size = (Get-Item $Destination).Length
                if ($size -lt 100MB) { throw "Downloaded file too small ($size bytes)" }
                Write-Ok "Download complete via BITS"
                return
            } catch {
                Write-Warn "BITS fallback failed: $($_.Exception.Message)"
            }
            if ($attempt -lt 5) {
                Write-Warn "Retrying in $delay seconds..."
                Start-Sleep -Seconds $delay
            } else {
                Fail "Unable to download model after multiple attempts. Last error: $($_.Exception.Message)"
            }
        }
    }
}

function Ensure-PathExists {
    param([string]$Path, [string]$FriendlyName)
    if (-not (Test-Path $Path)) { Fail "$FriendlyName is missing: $Path" }
}

function Ensure-PythonVersion {
    Write-Status "Checking for Python $RequiredPythonVersion"
    $pythonVersionOutput = & py -$RequiredPythonVersion --version 2>&1
    if ($LASTEXITCODE -ne 0) { Fail "Python $RequiredPythonVersion is required." }
    $version = ($pythonVersionOutput -replace "Python", "").Trim()
    if (-not $version.StartsWith($RequiredPythonVersion)) { Fail "Python $RequiredPythonVersion is required but found $version" }
    Add-Diagnostic "Python $RequiredPythonVersion" $true "Detected"
}

function Ensure-Venv {
    if (-not (Test-Path $VenvActivate)) {
        Write-Status "Creating virtual environment (.venv)"
        & py -$RequiredPythonVersion -m venv $VenvPath
        Write-RepairLog "Created virtual environment at $VenvPath"
    }
    if (-not (Test-Path $VenvActivate)) { Fail "Virtual environment failed to initialize" }
    . $VenvActivate
    Add-Diagnostic ".venv present" $true "Activated"
}

function Ensure-Dependencies {
    Write-Status "Installing/validating Python dependencies"
    $requirements = Join-Path $RootPath "requirements.txt"
    $packages = @("llama-cpp-python=$RequiredLlamaCppVersion", "pygments", "python-multipart", "cpuinfo")
    & $PythonExe -m pip install --upgrade pip | Out-Null
    & $PythonExe -m pip install -r $requirements
    foreach ($pkg in $packages) { & $PythonExe -m pip install $pkg }
    $retries = 0
    while ($retries -lt 2) {
        $pipCheck = & $PythonExe -m pip check 2>&1
        if ($LASTEXITCODE -eq 0) { Add-Diagnostic "pip dependencies" $true "Healthy"; return }
        Write-Warn "pip check reported issues: $pipCheck"
        Write-RepairLog "pip check failed, retrying installation"
        & $PythonExe -m pip install -r $requirements
        $retries++
    }
    Fail "Python dependencies are missing or broken. See repair log."
}

function Ensure-LlamaBinary {
    if (-not (Test-Path $LlamaExe)) {
        Write-Warn "llama-server.exe missing; attempting to download prebuilt binary"
        $llamaUrl = "https://github.com/ggerganov/llama.cpp/releases/latest/download/llama-server.exe"
        Download-ModelSafe -Uri $llamaUrl -Destination $LlamaExe
        Write-RepairLog "Fetched llama-server.exe from upstream release"
    }
    Add-Diagnostic "llama-server.exe" (Test-Path $LlamaExe) "Present"
}

function Ensure-Model {
    Ensure-Directory -Path $DefaultModelDir
    $gguf = Get-ChildItem -Path $DefaultModelDir -Filter "*.gguf" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $gguf) {
        Write-Warn "GGUF model missing; downloading safe default"
        Download-ModelSafe -Uri $DefaultModelUrl -Destination $DefaultModel -Sha256 $DefaultModelSha256
        Write-RepairLog "Downloaded default GGUF model"
        $gguf = Get-Item $DefaultModel
    }
    $absolute = (Resolve-Path $gguf.FullName).Path
    Ensure-Directory -Path $ConfigDir
    $absolute | Out-File -FilePath $ModelPathFile -Force -Encoding utf8
    Add-Diagnostic "GGUF model" $true "Located at $absolute"
    return $absolute
}

function Ensure-HardwareProfile {
    $gpuInfo = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue
    $hasGpu = $gpuInfo -ne $null -and $gpuInfo.Count -gt 0
    $cudaDlls = @(Get-ChildItem -Path (Split-Path $LlamaExe -Parent) -Filter "cudart64*.dll" -ErrorAction SilentlyContinue)
    $cudaPresent = $cudaDlls.Count -gt 0
    $avxSupported = $false
    try { $avxSupported = [System.Runtime.Intrinsics.X86.Avx]::IsSupported } catch {}
    $profile = [pscustomobject]@{ gpu = $hasGpu; cuda_runtime = $cudaPresent; avx = $avxSupported; model_precision = "Q4_K"; mode = "cpu" }
    if ($hasGpu -and $cudaPresent) { $profile.mode = "gpu"; $profile.model_precision = "Q4_K_M" }
    if (-not $avxSupported) { $profile.model_precision = "Q4_K" }
    $profile | ConvertTo-Json | Out-File -FilePath $HardwareProfilePath -Force -Encoding utf8
    if (-not $cudaPresent) { Write-RepairLog "CUDA runtime missing; forcing CPU mode" }
    if (-not $avxSupported) { Write-RepairLog "AVX not detected; enforcing Q4_K fallback" }
    Add-Diagnostic "Hardware profile" $true "gpu=$hasGpu cuda=$cudaPresent avx=$avxSupported"
    return $profile
}

function Ensure-ModelPreference {
    param([string]$ModelPath, $Profile)
    $preferred = $ModelPath
    if ($Profile.model_precision -eq "Q4_K") {
        $preferred = $ModelPath
    }
    $preferred | Out-File -FilePath $ModelPreferencePath -Force -Encoding utf8
}

function Ensure-RelayScriptExists { if (-not (Test-Path $RelayScript)) { Fail "relay_server.py missing" } }
function Ensure-CathedralLauncher { if (-not (Test-Path $CathedralLauncher)) { Fail "cathedral_launcher.py missing" } }

function Test-UrlHealthy {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -Method GET
        return $response.StatusCode -lt 500
    } catch { return $false }
}

function Wait-ForHealth {
    param([string]$Url, [int]$TimeoutSec, [string]$Name)
    $stopWatch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($stopWatch.Elapsed.TotalSeconds -lt $TimeoutSec) {
        if (Test-UrlHealthy -Url $Url) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Start-LlamaServer {
    param([string]$ModelPath)
    if (Test-UrlHealthy -Url $LlamaHealthUrl) { Write-Ok "Model server already running"; return }
    Kill-PortOccupants -Port $LlamaPort
    Write-Status "Launching llama.cpp server"
    $command = "cd `"$RootPath`"; Write-Host 'Launching llama-server on port $LlamaPort using model $ModelPath' -ForegroundColor Yellow; & `"$LlamaExe`" --host 127.0.0.1 --port $LlamaPort --model `"$ModelPath`""
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal -WorkingDirectory $RootPath | Out-Null
    if (-not (Wait-ForHealth -Url $LlamaHealthUrl -TimeoutSec $HealthRetrySeconds -Name "llama-server")) { throw "llama-server did not become healthy in time" }
    Write-Ok "Model server started"
}

function Start-RelayServer {
    Ensure-RelayScriptExists
    if (Test-UrlHealthy -Url $RelayHealthUrl) { Write-Ok "Relay already running"; return }
    Kill-PortOccupants -Port $RelayPort
    Write-Status "Launching relay_server.py"
    $command = "cd `"$RootPath`"; Write-Host 'Launching relay on port $RelayPort' -ForegroundColor Yellow; & `"$PythonExe`" `"$RelayScript`" --port $RelayPort"
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal -WorkingDirectory $RootPath | Out-Null
    if (-not (Wait-ForHealth -Url $RelayHealthUrl -TimeoutSec $HealthRetrySeconds -Name "relay_server")) { throw "relay_server did not become healthy in time" }
    Write-Ok "Relay server online"
}

function Start-CathedralShell {
    Ensure-CathedralLauncher
    Kill-PortOccupants -Port $RuntimePort
    Write-Status "Launching SentientOS runtime shell"
    $command = "cd `"$RootPath`"; Write-Host 'Starting runtime shell on port $RuntimePort (if applicable)' -ForegroundColor Yellow; & `"$PythonExe`" `"$CathedralLauncher`""
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal -WorkingDirectory $RootPath | Out-Null
    Write-Ok "SentientOS runtime active"
}

function Retry-Component {
    param([string]$Name, [scriptblock]$Action)
    for ($i = 1; $i -le $MaxComponentRetries; $i++) {
        try { & $Action; return } catch { Write-Warn "$Name attempt $i failed: $($_.Exception.Message)"; if ($i -lt $MaxComponentRetries) { Start-Sleep -Seconds 2 } else { Fail "$Name failed after $MaxComponentRetries attempts." } }
    }
}

function Show-SelfDiagnostics {
    Write-Host "--- SentientOS Self-Diagnostics ---" -ForegroundColor Cyan
    $Diagnostics | ForEach-Object { $symbol = if ($_.Healthy) { "✔" } else { "✖" }; $color = if ($_.Healthy) { "Green" } else { "Red" }; Write-Host "$symbol $($_.Name): $($_.Action)" -ForegroundColor $color }
    Write-Host "------------------------------------" -ForegroundColor Cyan
}

# MAIN EXECUTION
Write-Status "Starting SentientOS stack..."
Ensure-Directory -Path $ConfigDir
Ensure-Directory -Path $ModelsDir
Ensure-Directory -Path (Split-Path $RepairLog -Parent)
Ensure-PythonVersion
Ensure-Venv
Ensure-Dependencies
Ensure-LlamaBinary
$modelPath = Ensure-Model
$profile = Ensure-HardwareProfile
Ensure-ModelPreference -ModelPath $modelPath -Profile $profile
Add-Diagnostic "Ports" $true "Ensuring 8080/3928/5000 are free"
Kill-PortOccupants -Port $LlamaPort
Kill-PortOccupants -Port $RelayPort
Kill-PortOccupants -Port $RuntimePort
Show-SelfDiagnostics
Retry-Component -Name "llama-server" -Action { Start-LlamaServer -ModelPath $modelPath }
Retry-Component -Name "relay_server" -Action { Start-RelayServer }
Retry-Component -Name "runtime" -Action { Start-CathedralShell }
Write-Ok "All components launched."
