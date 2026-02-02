@echo off
setlocal
REM ==== SentientOS Repo Updater ====
set LOGFILE=%~dp0update_cathedral.log
set REPO_DIR=%~dp0

echo [%date% %time%] === Cathedral Update Started === >> "%LOGFILE%"
cd /d "%REPO_DIR%"

REM -- Pull latest code
echo [%date% %time%] git pull origin main >> "%LOGFILE%"
git pull origin main >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: git pull failed. >> "%LOGFILE%"
    exit /b 1
)

REM -- Run smoke tests
echo [%date% %time%] pip install -e .[dev] >> "%LOGFILE%"
python -m pip install -e .[dev] >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: pip install failed. >> "%LOGFILE%"
    exit /b 2
)

echo [%date% %time%] pytest -q >> "%LOGFILE%"
pytest -q >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: pytest failed. >> "%LOGFILE%"
    exit /b 3
)

echo [%date% %time%] python verify_audits.py --help >> "%LOGFILE%"
python verify_audits.py --help >> "%LOGFILE%" 2>&1

echo [%date% %time%] === Cathedral Update Complete === >> "%LOGFILE%"
echo Update complete! Logs written to %LOGFILE%.
exit /b 0
