@echo off
REM Launch SentientOS with optional GUI
setlocal
set LOGFILE=%~dp0launch_sentientos.log
set SCRIPT_DIR=%~dp0

if "%1"=="--nogui" goto NOGUI
if exist cathedral_gui.py (
    echo [%date% %time%] starting cathedral_gui.py >> "%LOGFILE%"
    python cathedral_gui.py >> "%LOGFILE%" 2>&1
    goto END
)
:NOGUI
python cathedral_launcher.py >> "%LOGFILE%" 2>&1
:END
endlocal
