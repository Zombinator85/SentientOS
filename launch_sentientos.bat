@echo off
setlocal
chcp 65001 > nul
title SentientOS Cathedral Launcher

set SCRIPT_DIR=%~dp0
cd /d %SCRIPT_DIR%

REM Ensure logs directory exists
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"
set LOGFILE=%SCRIPT_DIR%logs\launch_sentientos.log
echo [%date% %time%] === SentientOS Launch Started === >> "%LOGFILE%"

echo ~F Activating virtual environment (if exists)...
if exist "%SCRIPT_DIR%.venv\Scripts\activate.bat" (
    call "%SCRIPT_DIR%.venv\Scripts\activate.bat"
)

REM Optionally install requirements
if exist "%SCRIPT_DIR%requirements.txt" (
    echo ~R Installing dependencies...
    pip install -r requirements.txt
)

echo ~@ Starting SentientOS Relay (Flask)...
start cmd /k python sentient_api.py

echo ~D Starting Heartbeat (optional)...
REM Uncomment if you want to start heartbeat daemon:
REM start cmd /k python heartbeat.py

echo ~\ Starting Memory Digest Builder (optional)...
REM Uncomment if you want to stream memory logs into digest:
REM start cmd /k python digest_builder.py

echo ~Y Cathedral boot sequence initiated. All relays glowing.
echo [%date% %time%] SentientOS launch script complete. >> "%LOGFILE%"
pause

