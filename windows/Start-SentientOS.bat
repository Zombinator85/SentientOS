@echo off
setlocal

set "BASE_DIR=C:\SentientOS"
if not "%SENTIENTOS_BASE_DIR%"=="" set "BASE_DIR=%SENTIENTOS_BASE_DIR%"

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR%"=="" set "SCRIPT_DIR=.\"
pushd "%SCRIPT_DIR%.." >nul 2>&1
if errorlevel 1 (
    echo Failed to locate SentientOS repository directory from %SCRIPT_DIR%
    exit /b 1
)

set "VENV_DIR=%BASE_DIR%\venv"
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Virtual environment not found at %VENV_DIR%.
    echo Run windows\Install-SentientOS.ps1 before launching the demo.
    popd >nul 2>&1
    exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo Failed to activate virtual environment.
    popd >nul 2>&1
    exit /b 1
)

set "SENTIENTOS_BASE_DIR=%BASE_DIR%"

echo Starting SentientOS (Lumos) demo...
echo Press Ctrl+C to stop. Use Start-SentientOS.bat --no-demo to see the live dashboard without auto-running a demo.
echo.

if "%1"=="--no-demo" (
    python -m sentientos.cli.dashboard_cli
) else (
    python -m sentientos.cli.dashboard_cli --run-demo demo_simple_success
)

set "EXIT_CODE=%ERRORLEVEL%"
popd >nul 2>&1
exit /b %EXIT_CODE%
