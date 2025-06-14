@echo off
setlocal
chcp 65001 > nul
set SCRIPT_DIR=%~dp0
set LOGFILE=%SCRIPT_DIR%logs\relay_stdout.log
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"
if exist "%SCRIPT_DIR%venv\Scripts\activate.bat" (
    call "%SCRIPT_DIR%venv\Scripts\activate.bat"
)
if exist "%SCRIPT_DIR%requirements.txt" (
    pip install -r "%SCRIPT_DIR%requirements.txt"
)
start "SentientOS Relay" cmd /k python "%SCRIPT_DIR%sentient_api.py" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [ERROR] Relay failed. See %LOGFILE%
    pause
)
endlocal
