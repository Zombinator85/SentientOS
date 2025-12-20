#requires -version 5.1
<#$
Start-All.ps1 - Self-healing SentientOS launcher for Windows
- Safe GET-only downloader with retries and checksum validation
- Auto-repairs missing environments, binaries, and models
- Fixed to single-model (Mistral-7B) for Codex stability
- Frees conflicting ports (5000/8000/3928) and launches all components
- Writes diagnostic and repair history to logs/self_repair.log + logs/launcher.log
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[System.Reflection.Assembly]::LoadWithPartialName("System.IO.Compression.FileSystem") | Out-Null

# Paths
$RootPath = "C:\\SentientOS"
$ConfigDir = Join-Path $RootPath "config"
$HardwareProfilePath = Join-Path $ConfigDir "hardware_profile.json"
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

# Only this model exists now
$DefaultModelUrl = "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf?download=1"
$DefaultModelSha256 = "e6dfd3bd27cfa6f0595b234d79ce31775f5f52a12ca6c5075463996f856b503d"

$RepairLog = Join-Path $RootPath "logs\\self_repair.log"
$LauncherLog = Join-Path $RootPath "logs\\launcher.log"

# Ports
$RelayHost = "127.0.0.1"
$LlamaPort = 8000
$RelayPort = 3928
$RuntimePort = 5000
$LlamaHealthUrl = "http://127.0.0.1:$LlamaPort/"
$RelayHealthUrl = "http://$RelayHost:$RelayPort/health/status"
$RuntimeHealthUrl = "http://127.0.0.1:$RuntimePort/health"

# Config
$RequiredPythonVersion = "3.11"
$RequiredLlamaCppVersion = "0.2.90"
$StartupTimeoutSec = 120
$HealthRetrySeconds = 20
$MaxComponentRetries = 3

$Diagnostics = @()
$HardwareProfileChanged = $false

function Ensure-Directory { param([string]$Path) if (-not (Test-Path $Path)) { New-Item -ItemType Directory -Path $Path -Force | Out-Null } }

function Write-Log {
    param([string]$Message, [switch]$Repair)
    Ensure-Directory -Path (Split-Path $LauncherLog -Parent)
    $timestamp = (Get-Date).ToString("s") + "Z"
    Add-Content -Path $LauncherLog -Value "$timestamp`t$Message"
    if ($Repair) {
        Ensure-Directory -Path (Split-Path $RepairLog -Parent)
        Add-Content -Path $RepairLog -Value "$timestamp`t$Message"
    }
}
function Write-Status { param([string]$Message) Write-Host "[*] $Message" -ForegroundColor Cyan; Write-Log $Message }
function Write-Ok     { param([string]$Message) Write-Host "[✔] $Message" -ForegroundColor Green; Write-Log $Message }
function Write-Warn   { param([string]$Message) Write-Host "[✖] $Message" -ForegroundColor Yellow; Write-Log $Message -Repair }
function Fail {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    Write-Log $Message -Repair
    exit 1
}

function Add-Diagnostic {
    param([string]$Name, [bool]$Healthy, [string]$Action)
    $Diagnostics += [pscustomobject]@{ Name=$Name; Healthy=$Healthy; Action=$Action }
    $symbol = if ($Healthy) {"✔"} else {"✖"}
    $color = if ($Healthy) {"Green"} else {"Red"}
    Write-Host "$symbol $Name`t$Action" -ForegroundColor $color
    Write-Log "$symbol $Name $Action"
}

function Get-PortProcessIds {
    param([int]$Port)
    $c = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $c) { return @() }
    return $c | Select-Object -ExpandProperty OwningProcess -Unique
}

function Describe-PortOccupants {
    param([int]$Port)
    $p = Get-PortProcessIds -Port $Port
    if (-not $p -or $p.Count -eq 0) { return "none" }
    $out = @()
    foreach ($pid in $p) {
        try { $proc = Get-Process -Id $pid -ErrorAction Stop; $out += "$($proc.ProcessName):$pid" }
        catch { $out += "pid:$pid" }
    }
    return $out -join ", "
}

function Kill-PortOccupants {
    param([int]$Port)
    foreach ($pid in (Get-PortProcessIds $Port)) {
        try {
            Write-Status "Killing process $pid on port $Port"
            Stop-Process -Id $pid -Force
            Write-Log "Killed process $pid on port $Port" -Repair
        } catch { Write-Warn "Could not kill PID $pid on port $Port" }
    }
}

function Ensure-PortsClear { param([int[]]$Ports) foreach ($p in $Ports) {
    $occ = Describe-PortOccupants -Port $p
    if ($occ -ne "none") { Write-Warn "Port $p occupied by $occ; freeing"; Kill-PortOccupants -Port $p }
    else { Write-Ok "Port $p is free" }
}}

function Remove-ZombieProcesses {
    $patterns = @("llama-server", "relay_server.py", "cathedral_launcher.py")
    $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        foreach ($p in $patterns) { if ($_.Name -like "*$p*" -or $_.CommandLine -like "*$p*") { return $true } } return $false
    }
    foreach ($proc in $all) {
        try {
            Write-Status "Killing zombie $($proc.Name) (PID $($proc.ProcessId))"
            Stop-Process -Id $proc.ProcessId -Force
            Write-Log "Killed zombie process $($proc.Name)" -Repair
        } catch { Write-Warn "Failed to kill zombie PID $($proc.ProcessId)" }
    }
}

function Test-Checksums {
    param([string]$Path, [string]$Sha256)
    if (-not (Test-Path $Path)) { return $false }
    if (-not $Sha256) { return $true }
    $actual = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLower()
    return $actual -eq $Sha256.ToLower()
}

function Download-Model {
    param([string]$Url, [string]$Dest, [string]$Sha256)
    Ensure-Directory (Split-Path $Dest -Parent)
    $tmp = "$Dest.tmp"
    if (Test-Path $Dest -and (Test-Checksums $Dest $Sha256)) {
        Write-Ok "Model already valid"
        return $Dest
    }
    if (Test-Path $Dest) { Remove-Item $Dest -Force }
    Write-Status "Downloading model..."
    Invoke-WebRequest -Uri $Url -OutFile $tmp -UseBasicParsing
    if (-not (Test-Checksums $tmp $Sha256)) {
        Remove-Item $tmp -Force
        Fail "Checksum mismatch for model"
    }
    Move-Item $tmp $Dest -Force
    Write-Ok "Model downloaded and validated"
    return $Dest
}

function Ensure-PythonVersion {
    Write-Status "Checking Python $RequiredPythonVersion"
    $out = & py -$RequiredPythonVersion --version 2>&1
    if ($LASTEXITCODE -ne 0) { Fail "Python $RequiredPythonVersion not found" }
    if (-not $out.StartsWith("Python $RequiredPythonVersion")) { Fail "Wrong Python version: $out" }
    Add-Diagnostic "Python" $true $out
}

function Ensure-Venv {
    if (-not (Test-Path $VenvActivate)) {
        Write-Status "Creating virtual environment"
        & py -$RequiredPythonVersion -m venv $VenvPath
        Write-Log "Created venv" -Repair
    }
    . $VenvActivate
    if (-not (Test-Path $PythonExe)) { Fail "Venv Python missing" }
    Add-Diagnostic ".venv" $true "Active"
}

function Ensure-Dependencies {
    $req = Join-Path $RootPath "requirements.txt"
    Write-Status "Installing dependencies"
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -r $req
    & $PythonExe -m pip install "llama-cpp-python==$RequiredLlamaCppVersion"
    Add-Diagnostic "pip deps" $true "Installed"
}

function Ensure-LlamaBinary {
    if (-not (Test-Path $LlamaExe)) {
        Write-Warn "llama-server.exe missing, downloading..."
        $url = "https://github.com/ggerganov/llama.cpp/releases/latest/download/llama-server.exe"
        Invoke-WebRequest -Uri $url -OutFile $LlamaExe -UseBasicParsing
        Write-Log "Downloaded llama-server.exe" -Repair
    }
    Add-Diagnostic "llama-server.exe" $true "Present"
}

function Ensure-Model {
    Ensure-Directory $DefaultModelDir
    if (-not (Test-Path $DefaultModel)) {
        Download-Model -Url $DefaultModelUrl -Dest $DefaultModel -Sha256 $DefaultModelSha256
    }
    Add-Diagnostic "GGUF model" $true $DefaultModel
    $resolved = (Resolve-Path $DefaultModel).Path
    $resolved | Out-File $ModelPathFile -Encoding utf8 -Force
    return $resolved
}

function Ensure-HardwareProfile {
    $gpu = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue
    $names = @(); $vram = 0
    foreach ($g in $gpu) { $names += $g.Name; $vram += [int64]$g.AdapterRAM }
    $ram = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
    $profile = [pscustomobject]@{
        gpu=$names
        vram_gb=[math]::Round($vram/1GB,2)
        ram_gb=[math]::Round($ram/1GB,2)
    }
    $json = $profile | ConvertTo-Json
    if (-not (Test-Path $HardwareProfilePath)) {
        $json | Out-File $HardwareProfilePath -Force
    } else {
        $existing = Get-Content $HardwareProfilePath -Raw
        if ($existing -ne $json) {
            $HardwareProfileChanged = $true
            Write-Warn "Hardware changed since last run"
            $json | Out-File $HardwareProfilePath -Force
        }
    }
    Add-Diagnostic "Hardware" $true ("GPU=" + ($names -join ", "))
}

function Test-UrlHealthy {
    param([string]$Url)
    try { 
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5; 
        return $r.StatusCode -lt 500 
    } catch { return $false }
}

function Wait-ForHealth {
    param([string]$Url, [string]$Name)
    Write-Status "Waiting for $Name..."
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $HealthRetrySeconds) {
        if (Test-UrlHealthy $Url) { return $true }
        Start-Sleep 2
    }
    return $false
}

function Start-LlamaServer {
    param([string]$Model)
    if (Test-UrlHealthy $LlamaHealthUrl) { Write-Ok "Model server already running"; return }
    Kill-PortOccupants $LlamaPort
    Write-Status "Launching llama.cpp"
    $cmd = "cd `"$RootPath`"; & `"$LlamaExe`" --host 127.0.0.1 --port $LlamaPort --model `"$Model`""
    Start-Process powershell -ArgumentList "-NoExit","-Command",$cmd -WorkingDirectory $RootPath
    if (-not (Wait-ForHealth $LlamaHealthUrl "llama-server")) { Fail "llama-server failed to start" }
    Write-Ok "llama-server running"
}

function Start-RelayServer {
    if (Test-UrlHealthy $RelayHealthUrl) { Write-Ok "Relay already running"; return }
    Kill-PortOccupants $RelayPort
    Write-Status "Launching relay_server.py"
    $cmd = "cd `"$RootPath`"; & `"$PythonExe`" `"$RelayScript`" --host $RelayHost --port $RelayPort --llama-host 127.0.0.1 --llama-port $LlamaPort"
    Start-Process powershell -ArgumentList "-NoExit","-Command",$cmd -WorkingDirectory $RootPath
    if (-not (Wait-ForHealth $RelayHealthUrl "relay")) { Fail "relay_server failed to start" }
    Write-Ok "relay_server running"
}

function Start-CathedralShell {
    Kill-PortOccupants $RuntimePort
    Write-Status "Launching Runtime"
    $cmd = "cd `"$RootPath`"; & `"$PythonExe`" `"$CathedralLauncher`" --attach-relay --relay-host $RelayHost --relay-port $RelayPort --model-port $LlamaPort"
    Start-Process powershell -ArgumentList "-NoExit","-Command",$cmd -WorkingDirectory $RootPath
    Write-Ok "Runtime launched"
}

function Retry-Component {
    param([string]$Name, [scriptblock]$Action)
    for ($i=1; $i -le $MaxComponentRetries; $i++) {
        try { & $Action; return } 
        catch { Write-Warn "$Name attempt $i failed: $($_.Exception.Message)" }
    }
    Fail "$Name failed after $MaxComponentRetries attempts"
}

function Show-SelfDiagnostics {
    Write-Host "`n--- SELF DIAGNOSTICS ---" -ForegroundColor Cyan
    foreach ($d in $Diagnostics) {
        $sym = if ($d.Healthy) {"✔"} else {"✖"}
        $color = if ($d.Healthy) {"Green"} else {"Red"}
        Write-Host "$sym $($d.Name): $($d.Action)" -ForegroundColor $color
    }
    Write-Host "--------------------------`n" -ForegroundColor Cyan
}

# MAIN EXECUTION
Write-Status "Starting SentientOS stack..."

Ensure-Directory $ConfigDir
Ensure-Directory $ModelsDir
Ensure-Directory (Split-Path $RepairLog -Parent)
Ensure-Directory (Split-Path $LauncherLog -Parent)

Remove-ZombieProcesses
Ensure-PythonVersion
Ensure-Venv
Ensure-Dependencies
Ensure-LlamaBinary
Ensure-HardwareProfile
$modelPath = Ensure-Model

Ensure-PortsClear @($LlamaPort,$RelayPort,$RuntimePort)
Show-SelfDiagnostics

Retry-Component "llama-server" { Start-LlamaServer -Model $modelPath }
Retry-Component "relay_server" { Start-RelayServer }
Retry-Component "runtime"      { Start-CathedralShell }

Write-Ok "All components launched successfully."
