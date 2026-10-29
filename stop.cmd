@echo off
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Windows Python Launcher is required. Existing records were not changed.
  pause
  exit /b 1
)
py -3.13 "%~dp0launcher.py" stop
set "taskExit=%errorlevel%"
pause
exit /b %taskExit%
