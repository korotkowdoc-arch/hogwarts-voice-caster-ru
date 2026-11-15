@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Run install.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m hogwarts_voice %*
pause
