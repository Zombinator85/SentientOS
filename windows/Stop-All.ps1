#requires -version 5.1
<#
Stop-All.ps1 - Terminates SentientOS Windows stack
- Stops llama.cpp, relay, runtime Python shells, and stray PowerShell windows
- Frees listening ports and removes temporary lock files
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Join-Path $PSScriptRoot ".."
Set-Location $Root

$Ports = @(8080, 3928, 5000)
$LogPath = Join-Path $Root "logs\startup.log"

function Write-Log {
    param([string]$Level, [string]$Message)
    $timestamp = (Get-Date).ToString("s")
    $line = "[$timestamp][$Level] $Message"
    $dir = Split-Path $LogPath -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    if (-not (Test-Path $LogPath)) { New-Item -ItemType File -Path $LogPath -Force | Out-Null }
    Add-Content -Path $LogPath -Value $line
    $color = switch ($Level) {
        "INFO" { "Cyan" }
        "WARN" { "Yellow" }
        "ERROR" { "Red" }
        default { "Gray" }
    }
    Write-Host $line -ForegroundColor $color
}

function Stop-ProcessByPattern {
    param([string]$Pattern)
    $matches = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match $Pattern }
    foreach ($proc in $matches) {
        try {
            Write-Log -Level "INFO" -Message "Stopping PID $($proc.ProcessId) for pattern '$Pattern'"
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        } catch {
            Write-Log -Level "WARN" -Message "Failed to stop PID $($proc.ProcessId): $($_.Exception.Message)"
        }
    }
}

function Stop-ByName {
    param([string]$Name)
    $procs = Get-Process -Name $Name -ErrorAction SilentlyContinue
    foreach ($proc in $procs) {
        try {
            Write-Log -Level "INFO" -Message "Stopping $Name (PID $($proc.Id))"
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
        } catch {
            Write-Log -Level "WARN" -Message "Unable to stop $Name (PID $($proc.Id)): $($_.Exception.Message)"
        }
    }
}

function Free-Port {
    param([int]$Port)
    $matches = netstat -ano | Select-String ":$Port"
    foreach ($line in $matches) {
        $pid = ($line -split "\s+")[-1]
        if ($pid -match "^\d+$") {
            try {
                Write-Log -Level "INFO" -Message "Killing PID $pid holding port $Port"
                taskkill /PID $pid /F | Out-Null
            } catch {
                Write-Log -Level "WARN" -Message "Failed to kill PID $pid on port $Port: $($_.Exception.Message)"
            }
        }
    }
}

function Clean-Locks {
    $locks = @(Get-ChildItem -Path (Join-Path $Root "sentientos_data") -Filter "*.lock" -Recurse -ErrorAction SilentlyContinue)
    foreach ($file in $locks) {
        try {
            Remove-Item -Path $file.FullName -Force -ErrorAction Stop
            Write-Log -Level "INFO" -Message "Removed lockfile $($file.FullName)"
        } catch {
            Write-Log -Level "WARN" -Message "Could not remove lockfile $($file.FullName): $($_.Exception.Message)"
        }
    }
}

Write-Log -Level "INFO" -Message "Stopping SentientOS stack..."
Stop-ByName -Name "llama-server"
Stop-ProcessByPattern -Pattern "relay_server.py"
Stop-ProcessByPattern -Pattern "sentient_shell.py"
Stop-ProcessByPattern -Pattern "cathedral_launcher.py"
Stop-ByName -Name "powershell"  # catch stuck consoles started by the launcher

foreach ($port in $Ports) { Free-Port -Port $port }
Clean-Locks

Write-Log -Level "INFO" -Message "Shutdown complete."
