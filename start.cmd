@echo off
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Python 3.13 64-bit and Windows Python Launcher are required.
  echo https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
py -3.13 "%~dp0launcher.py" start
set "taskExit=%errorlevel%"
pause
exit /b %taskExit%
