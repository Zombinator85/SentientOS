@echo off
setlocal
chcp 65001 > nul

set SCRIPT_DIR=%~dp0
set LOGFILE=%SCRIPT_DIR%logs\launch_sentientos.log
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

REM Optional: activate virtualenv
if exist "%SCRIPT_DIR%venv\Scripts\activate.bat" (
    call "%SCRIPT_DIR%venv\Scripts\activate.bat"
)

REM Optional: install requirements
if exist "%SCRIPT_DIR%requirements.txt" (
    pip install -r "%SCRIPT_DIR%requirements.txt"
)

REM Handle GUI mode unless explicitly skipped
if "%1"=="--nogui" goto NOGUI

if exist "%SCRIPT_DIR%cathedral_gui.py" (
    echo [%date% %time%] Starting GUI >> "%LOGFILE%"
    start "Cathedral GUI" cmd /k python "%SCRIPT_DIR%cathedral_gui.py" >> "%LOGFILE%" 2>&1
    goto END
)

:NOGUI
echo [%date% %time%] Starting fallback relay >> "%LOGFILE%"
start "SentientOS Relay" cmd /k python "%SCRIPT_DIR%sentient_api.py" >> "%LOGFILE%" 2>&1

:END
endlocal
