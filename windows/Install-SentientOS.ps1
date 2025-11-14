[CmdletBinding()]
param(
    [string]$BaseDir,
    [string]$PythonExe
)

$ErrorActionPreference = "Stop"
$defaultBase = "C:\SentientOS"

if (-not $BaseDir -or [string]::IsNullOrWhiteSpace($BaseDir)) {
    $inputValue = Read-Host -Prompt "Enter base directory for SentientOS [`$defaultBase`]"
    if ([string]::IsNullOrWhiteSpace($inputValue)) {
        $BaseDir = $defaultBase
    } else {
        $BaseDir = $inputValue
    }
}

if (-not $PythonExe -or [string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = "python"
    if (-not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
        if (Get-Command "py" -ErrorAction SilentlyContinue) {
            $PythonExe = "py"
        } else {
            throw "Unable to locate a Python interpreter. Please install Python 3.10+ and rerun the installer."
        }
    }
}

$resolvedBase = Resolve-Path -Path $BaseDir -ErrorAction SilentlyContinue
if ($resolvedBase) {
    $BaseDir = $resolvedBase.Path
}
$BaseDir = [System.IO.Path]::GetFullPath($BaseDir)
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Write-Host "Installing SentientOS demo into $BaseDir" -ForegroundColor Cyan

$directories = @(
    $BaseDir,
    (Join-Path $BaseDir "logs"),
    (Join-Path $BaseDir "sentientos_data"),
    (Join-Path $BaseDir "sentientos_data\models"),
    (Join-Path $BaseDir "sentientos_data\config")
)
foreach ($dir in $directories) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

$venvDir = Join-Path $BaseDir "venv"
if (-not (Test-Path $venvDir)) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Cyan
    & $PythonExe -m venv $venvDir
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment appears to be corrupt. Expected $venvPython"
}

Push-Location $repoRoot
try {
    Write-Host "Upgrading pip..." -ForegroundColor Cyan
    & $venvPython -m pip install --upgrade pip

    Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
    & $venvPython -m pip install -r requirements.txt
}
finally {
    Pop-Location
}

$env:SENTIENTOS_BASE_DIR = $BaseDir
try {
    Write-Host "Initializing SentientOS configuration..." -ForegroundColor Cyan
    & $venvPython -m sentientos.start --init-only
} finally {
    Remove-Item Env:SENTIENTOS_BASE_DIR -ErrorAction SilentlyContinue
}

$configPath = Join-Path $BaseDir "sentientos_data\config\runtime.json"
if (Test-Path $configPath) {
    $configJson = Get-Content -Path $configPath -Raw | ConvertFrom-Json
    $modelPathValue = $configJson.runtime.model_path
    if ($modelPathValue) {
        if ([System.IO.Path]::IsPathRooted($modelPathValue)) {
            $modelPath = $modelPathValue
        } else {
            $modelPath = Join-Path $BaseDir $modelPathValue
        }
        if (-not (Test-Path $modelPath)) {
            Write-Warning "Mixtral model not found at $modelPath. Please place your GGUF file here before running the demo."
        }
    }
} else {
    Write-Warning "Runtime configuration not found at $configPath."
}

Write-Host "SentientOS demo installation complete." -ForegroundColor Green
Write-Host "Use windows\\Start-SentientOS.bat to launch the console dashboard." -ForegroundColor Green
