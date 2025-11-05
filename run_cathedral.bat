@echo off
REM Cross-platform launcher for SentientOS
REM Calls cathedral_launcher.py and logs to run_cathedral.log
setlocal
set LOGFILE=%~dp0run_cathedral.log
set SCRIPT_DIR=%~dp0

set LUMOS_AUTO_APPROVE=1
set SENTIENTOS_HEADLESS=1

echo [%date% %time%] === Cathedral Launch Started === >> "%LOGFILE%"
cd /d "%SCRIPT_DIR%"
python gpu_autosetup.py >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] WARNING: gpu_autosetup.py reported a non-zero exit code. >> "%LOGFILE%"
)
python cathedral_launcher.py >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: cathedral_launcher.py failed. >> "%LOGFILE%"
    exit /b 1
)

echo [%date% %time%] Cathedral launch complete. >> "%LOGFILE%"
endlocal
