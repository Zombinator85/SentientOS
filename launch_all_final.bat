@echo off
setlocal
set LOGFILE=%~dp0launch_all_final.log
set SCRIPT_DIR=%~dp0

echo [%date% %time%] === Cathedral Launch Started === >> "%LOGFILE%"
cd /d "%SCRIPT_DIR%"
python cathedral_launcher.py >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: cathedral_launcher.py failed. >> "%LOGFILE%"
    exit /b 1
)

echo [%date% %time%] Cathedral launch complete. >> "%LOGFILE%"
endlocal
