#requires -version 5.1
<#$
Start-All.ps1 - Self-healing SentientOS launcher for Windows
- Safe, GET-only downloader with retries and checksum validation
- Auto-repairs missing environments, binaries, and models
- Detects hardware (GPU/CUDA/AVX/RAM/VRAM) and enforces correct model selection
- Frees conflicting ports (5000/8000/3928) and launches components in their own windows
- Writes diagnostic and repair history to logs/self_repair.log and logs/launcher.log
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
$PhiMiniDir = Join-Path $ModelsDir "phi-3-mini-4k"
$PhiMiniModel = Join-Path $PhiMiniDir "Phi-3-mini-4k-instruct-q4.gguf"
$QwenSmallDir = Join-Path $ModelsDir "qwen2.5-3b"
$QwenSmallModel = Join-Path $QwenSmallDir "qwen2.5-3b-instruct-q4_k_m.gguf"
$RepairLog = Join-Path $RootPath "logs\\self_repair.log"
$LauncherLog = Join-Path $RootPath "logs\\launcher.log"

# Configuration
$LlamaPort = 8000
$RelayPort = 3928
$RuntimePort = 5000
$LlamaHealthUrl = "http://127.0.0.1:$LlamaPort/"
$RelayHealthUrl = "http://127.0.0.1:$RelayPort/v1/health"
$RuntimeHealthUrl = "http://127.0.0.1:$RuntimePort/health"
$StartupTimeoutSec = 120
$HealthRetrySeconds = 20
$MaxComponentRetries = 3
$RequiredPythonVersion = "3.11"
$RequiredLlamaCppVersion = "0.2.90"
$DefaultModelUrl = "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf?download=1"
$DefaultModelSha256 = "e6dfd3bd27cfa6f0595b234d79ce31775f5f52a12ca6c5075463996f856b503d"
$PhiMiniUrl = "https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf"
$PhiMiniSha256 = ""
$QwenSmallUrl = "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
$QwenSmallSha256 = ""

$Diagnostics = @()
$HardwareProfileChanged = $false

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Write-Log {
    param(
        [string]$Message,
        [switch]$Repair
    )
    Ensure-Directory -Path (Split-Path $LauncherLog -Parent)
    $timestamp = (Get-Date).ToString("s") + "Z"
    Add-Content -Path $LauncherLog -Value "$timestamp`t$Message"
    if ($Repair) {
        Ensure-Directory -Path (Split-Path $RepairLog -Parent)
        Add-Content -Path $RepairLog -Value "$timestamp`t$Message"
    }
}

function Write-RepairLog { param([string]$Message) Write-Log -Message $Message -Repair }

function Write-Status { param([string]$Message) Write-Host "[*] $Message" -ForegroundColor Cyan; Write-Log -Message $Message }
function Write-Ok { param([string]$Message) Write-Host "[✔] $Message" -ForegroundColor Green; Write-Log -Message $Message }
function Write-Warn { param([string]$Message) Write-Host "[✖] $Message" -ForegroundColor Yellow; Write-Log -Message $Message -Repair }
function Fail {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    Write-RepairLog $Message
    Write-Log -Message "Launch failed: $Message"
    [void](Read-Host "Press Enter to close the launcher")
    exit 1
}

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
    Write-Log -Message "$symbol $Name`t$Action"
}

function Get-PortProcessIds {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $connections) { return @() }
    return $connections | Select-Object -ExpandProperty OwningProcess -Unique
}

function Describe-PortOccupants {
    param([int]$Port)
    $pids = Get-PortProcessIds -Port $Port
    if (-not $pids -or $pids.Count -eq 0) { return "none" }
    $details = @()
    foreach ($pid in $pids) {
        try {
            $proc = Get-Process -Id $pid -ErrorAction Stop
            $details += "$($proc.ProcessName):$pid"
        } catch {
            $details += "pid:$pid"
        }
    }
    return $details -join ", "
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

function Ensure-PortsClear {
    param([int[]]$Ports)
    foreach ($port in $Ports) {
        $occupants = Describe-PortOccupants -Port $port
        if ($occupants -ne "none") {
            Write-Warn "Port $port occupied by $occupants; cleaning up"
            Kill-PortOccupants -Port $port
        } else {
            Write-Ok "Port $port is free"
        }
    }
}

function Remove-ZombieProcesses {
    $patterns = @("llama-server", "relay_server.py", "cathedral_launcher.py")
    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        foreach ($pattern in $patterns) { if ($_.CommandLine -like "*${pattern}*" -or $_.Name -like "*${pattern}*") { return $true } }
        return $false
    }
    foreach ($proc in $processes) {
        try {
            Write-Status "Stopping zombie process $($proc.Name) (PID $($proc.ProcessId))"
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-RepairLog "Terminated zombie process $($proc.Name) (PID $($proc.ProcessId))"
        } catch {
            Write-Warn "Unable to stop zombie process $($proc.ProcessId): $($_.Exception.Message)"
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
    if (-not (Test-Path $PythonExe)) { Fail "Virtual environment Python missing at $PythonExe" }
    $pipVersion = & $PythonExe -m pip --version 2>&1
    if ($LASTEXITCODE -ne 0) { Fail "pip is unavailable in the virtual environment" }
    Add-Diagnostic ".venv present" $true "Activated ($pipVersion)"
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

function Get-HardwareProfile {
    $gpuInfo = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue
    $gpuNames = @()
    $vramBytes = 0
    if ($gpuInfo) {
        foreach ($gpu in $gpuInfo) {
            $gpuNames += $gpu.Name
            $vramBytes += [int64]$gpu.AdapterRAM
        }
    }
    $cudaDlls = @(Get-ChildItem -Path (Split-Path $LlamaExe -Parent) -Filter "cudart64*.dll" -ErrorAction SilentlyContinue)
    $cudaPresent = $cudaDlls.Count -gt 0 -or (Test-Path "$env:WINDIR\System32\nvcuda.dll")
    $avxSupported = $false
    try { $avxSupported = [System.Runtime.Intrinsics.X86.Avx]::IsSupported } catch {}
    $ramBytes = (Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).TotalPhysicalMemory
    $ramGb = if ($ramBytes) { [math]::Round($ramBytes / 1GB, 2) } else { 0 }
    $vramGb = if ($vramBytes -gt 0) { [math]::Round($vramBytes / 1GB, 2) } else { 0 }
    return [pscustomobject]@{
        gpu_names      = $gpuNames
        cuda_runtime   = $cudaPresent
        avx            = $avxSupported
        ram_gb         = $ramGb
        vram_gb        = $vramGb
        timestamp      = (Get-Date).ToString("s") + "Z"
    }
}

function Ensure-HardwareProfile {
    $currentProfile = Get-HardwareProfile
    $existingProfile = $null
    if (Test-Path $HardwareProfilePath) {
        try { $existingProfile = Get-Content -Path $HardwareProfilePath -Raw | ConvertFrom-Json } catch {}
    }
    $currentJson = $currentProfile | ConvertTo-Json -Depth 6
    $existingJson = if ($existingProfile) { $existingProfile | ConvertTo-Json -Depth 6 } else { "" }
    if ($currentJson -ne $existingJson) {
        $HardwareProfileChanged = $true
        if ($existingJson -ne "") { Write-RepairLog "Hardware change detected; refreshing model selection" }
    }
    $currentJson | Out-File -FilePath $HardwareProfilePath -Force -Encoding utf8
    if ($currentProfile.gpu_names.Count -gt 0 -and -not $currentProfile.cuda_runtime) { Write-Warn "GPU detected ($($currentProfile.gpu_names -join ', ')) but CUDA runtime missing" }
    if (-not $currentProfile.avx) { Write-Warn "AVX not detected; enforcing CPU-safe quantization" }
    Add-Diagnostic "Hardware profile" $true "gpu=$($currentProfile.gpu_names -join ',') cuda=$($currentProfile.cuda_runtime) avx=$($currentProfile.avx) ram=${($currentProfile.ram_gb)}GB vram=${($currentProfile.vram_gb)}GB"
    return $currentProfile
}

function Get-ModelOptions {
    return @(
        [pscustomobject]@{ Name = "mistral-7b"; Path = $DefaultModel; Url = $DefaultModelUrl; Sha = $DefaultModelSha256; MinRamGB = 16; MinVramGB = 8; Precision = "Q4_K_M"; Size = "7B" },
        [pscustomobject]@{ Name = "phi-3-mini-4k"; Path = $PhiMiniModel; Url = $PhiMiniUrl; Sha = $PhiMiniSha256; MinRamGB = 12; MinVramGB = 6; Precision = "Q4"; Size = "4B" },
        [pscustomobject]@{ Name = "qwen2.5-3b"; Path = $QwenSmallModel; Url = $QwenSmallUrl; Sha = $QwenSmallSha256; MinRamGB = 8; MinVramGB = 4; Precision = "Q4_K_M"; Size = "3B" }
    )
}

function Ensure-ModelAsset {
    param([pscustomobject]$Option)
    $destDir = Split-Path $Option.Path -Parent
    Ensure-Directory -Path $destDir
    if (-not (Test-Path $Option.Path)) {
        Write-Warn "Model $($Option.Name) missing; downloading $($Option.Url)"
        Download-ModelSafe -Uri $Option.Url -Destination $Option.Path -Sha256 $Option.Sha
        Write-RepairLog "Fetched $($Option.Size) model from $($Option.Url)"
    }
    if (-not (Test-Path $Option.Path)) { Fail "Model asset $($Option.Path) missing after download" }
    return (Resolve-Path $Option.Path).Path
}

function Select-ModelOption {
    param($Profile)
    $options = Get-ModelOptions
    $rationale = @()
    if (-not $Profile.cuda_runtime) { $rationale += "CUDA runtime missing; selecting CPU-friendly quantization" }
    $eligible = $options | Where-Object { $Profile.ram_gb -ge $_.MinRamGB }
    $selected = $options | Where-Object { $_.Name -eq "mistral-7b" } | Select-Object -First 1
    if (-not $eligible) {
        $selected = $options[-1]
        $rationale += "Insufficient RAM ($($Profile.ram_gb) GB); falling back to smallest model"
    } elseif ($Profile.cuda_runtime -and $Profile.vram_gb -lt $selected.MinVramGB) {
        $rationale += "VRAM $($Profile.vram_gb) GB below 7B requirement $($selected.MinVramGB) GB; downsizing"
        $selected = ($options | Where-Object { $Profile.vram_gb -ge $_.MinVramGB -and $Profile.ram_gb -ge $_.MinRamGB } | Sort-Object -Property MinRamGB -Descending | Select-Object -First 1)
    } elseif ($Profile.ram_gb -lt $selected.MinRamGB) {
        $rationale += "RAM $($Profile.ram_gb) GB below 7B requirement $($selected.MinRamGB) GB; downsizing"
        $selected = ($eligible | Sort-Object -Property MinRamGB -Descending | Select-Object -First 1)
    }
    if (-not $selected) { $selected = $options[-1]; $rationale += "No eligible model matched; defaulting to smallest" }
    return @{ Option = $selected; Rationale = $rationale }
}

function Ensure-ModelPreference {
    param($Profile)
    $selection = Select-ModelOption -Profile $Profile
    $modelPath = Ensure-ModelAsset -Option $selection.Option
    Ensure-Directory -Path $ConfigDir
    $modelPath | Out-File -FilePath $ModelPathFile -Force -Encoding utf8
    $preferenceLines = @("model_path=$modelPath", "model_size=$($selection.Option.Size)", "precision=$($selection.Option.Precision)")
    if ($selection.Rationale.Count -gt 0) {
        $preferenceLines += "rationale=$($selection.Rationale -join '; ')"
        foreach ($reason in $selection.Rationale) { Write-RepairLog $reason }
    }
    $preferenceLines | Out-File -FilePath $ModelPreferencePath -Force -Encoding utf8
    Add-Diagnostic "Model selection" $true "${($selection.Option.Size)} at $modelPath"
    return $modelPath
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
    Write-Status "Waiting for $Name health at $Url (timeout ${TimeoutSec}s)"
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
    $proc = Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal -WorkingDirectory $RootPath -PassThru
    if (-not (Wait-ForHealth -Url $LlamaHealthUrl -TimeoutSec $HealthRetrySeconds -Name "llama-server")) {
        if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
        throw "llama-server did not become healthy in time"
    }
    Write-Ok "Model server started"
}

function Start-RelayServer {
    Ensure-RelayScriptExists
    if (Test-UrlHealthy -Url $RelayHealthUrl) { Write-Ok "Relay already running"; return }
    Kill-PortOccupants -Port $RelayPort
    Write-Status "Launching relay_server.py"
    $command = "cd `"$RootPath`"; Write-Host 'Launching relay on port $RelayPort' -ForegroundColor Yellow; & `"$PythonExe`" `"$RelayScript`" --port $RelayPort"
    $proc = Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal -WorkingDirectory $RootPath -PassThru
    if (-not (Wait-ForHealth -Url $RelayHealthUrl -TimeoutSec $HealthRetrySeconds -Name "relay_server")) {
        if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
        throw "relay_server did not become healthy in time"
    }
    Write-Ok "Relay server online"
}

function Start-CathedralShell {
    Ensure-CathedralLauncher
    Kill-PortOccupants -Port $RuntimePort
    Write-Status "Launching SentientOS runtime shell"
    $command = "cd `"$RootPath`"; Write-Host 'Starting runtime shell on port $RuntimePort (if applicable)' -ForegroundColor Yellow; & `"$PythonExe`" `"$CathedralLauncher`""
    $proc = Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal -WorkingDirectory $RootPath -PassThru
    $healthy = $false
    if (Wait-ForHealth -Url $RuntimeHealthUrl -TimeoutSec $HealthRetrySeconds -Name "runtime") { $healthy = $true }
    elseif ($proc -and -not $proc.HasExited) {
        Write-Warn "Runtime health endpoint unavailable; process is running"
        $healthy = $true
    }
    if (-not $healthy) { throw "Runtime failed to start" }
    Write-Ok "SentientOS runtime active"
}

function Retry-Component {
    param([string]$Name, [scriptblock]$Action)
    for ($i = 1; $i -le $MaxComponentRetries; $i++) {
        try {
            & $Action
            Write-Log -Message "$Name started successfully on attempt $i"
            return
        } catch {
            $message = "$Name attempt $i failed: $($_.Exception.Message)"
            Write-Warn $message
            if ($i -lt $MaxComponentRetries) {
                Start-Sleep -Seconds 2
            } else {
                Fail "$Name failed after $MaxComponentRetries attempts."
            }
        }
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
Ensure-Directory -Path (Split-Path $LauncherLog -Parent)
Remove-ZombieProcesses
Ensure-PythonVersion
Ensure-Venv
Ensure-Dependencies
Ensure-LlamaBinary
$profile = Ensure-HardwareProfile
$modelPath = Ensure-ModelPreference -Profile $profile
if ($HardwareProfileChanged) { Write-Warn "Hardware profile changed since last run; model preference refreshed" }
Add-Diagnostic "Ports" $true "Ensuring 8000/3928/5000 are free"
Ensure-PortsClear -Ports @($LlamaPort, $RelayPort, $RuntimePort)
Show-SelfDiagnostics
Retry-Component -Name "llama-server" -Action { Start-LlamaServer -ModelPath $modelPath }
Retry-Component -Name "relay_server" -Action { Start-RelayServer }
Retry-Component -Name "runtime" -Action { Start-CathedralShell }
Write-Ok "All components launched."
