@echo off
chcp 65001 >nul
title SentientOS Cathedral Launcher
cd /d %~dp0

echo 🔆 Activating virtual environment (if exists)...
if exist venv (
    call venv\Scripts\activate.bat
)

echo 🚀 Starting SentientOS Relay (Flask)...
start cmd /k python scripts\sentient_api.py

echo 🔄 Starting Heartbeat (optional)...
REM Uncomment if you want to start heartbeat daemon:
REM start cmd /k python scripts\heartbeat_mixtral.py

echo 📜 Starting Memory Digest Builder (optional)...
REM Uncomment if you want to stream memory logs into digest:
REM start cmd /k python scripts\digest_builder.py

echo 💙 Cathedral boot sequence initiated. All relays glowing.
pause
