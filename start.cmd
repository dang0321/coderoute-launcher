@echo off
cd /d "%~dp0"
if exist "%~dp0.coderoute\home\.venv\Scripts\python.exe" (
  "%~dp0.coderoute\home\.venv\Scripts\python.exe" "%~dp0launcher.py" start
  goto complete
)
for %%V in (3.13 3.12 3.11) do (
  py -%%V -c "import sys,struct; sys.exit(0 if sys.implementation.name=='cpython' and struct.calcsize('P')==8 else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "coderoutePythonVersion=%%V"
    goto useLauncher
  )
)
python -c "import sys,struct; sys.exit(0 if sys.implementation.name=='cpython' and sys.version_info[:2] in ((3,11),(3,12),(3,13)) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if not errorlevel 1 (
  python "%~dp0launcher.py" start
  goto complete
)
echo Windows CPython 3.11, 3.12 or 3.13 64-bit is required. PyPy is not supported.
echo https://www.python.org/downloads/windows/
pause
exit /b 1
:useLauncher
py -%coderoutePythonVersion% "%~dp0launcher.py" start
:complete
set "taskExit=%errorlevel%"
pause
exit /b %taskExit%
